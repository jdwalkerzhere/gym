from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import yaml

from .codex import Codex
from .db import completed_ids, connect, declared_observations, mastery_context, record
from .exercises import TYPES, discover, generation_contract, next_identity, read_exercise
from .product import preflight

IGNORED_PARTS = {".git", ".venv", ".pytest_cache", "__pycache__"}


def _files(root: Path) -> dict[Path, str]:
    return {path: (hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<directory>")
            for path in root.rglob("*") if not (set(path.relative_to(root).parts) & IGNORED_PARTS)}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def generate(root: Path, kind: str, codex: Codex | None = None):
    if kind not in TYPES:
        raise ValueError(f"unknown exercise type: {kind}")
    pack = preflight(root)
    exercise_id, order, path = next_identity(root, kind)
    db = connect(root)
    context = mastery_context(db)
    context["unseen_capabilities"] = sorted(pack["capability_ids"] - {row["capability_id"] for row in context["mastery"]})
    context["untested_dimensions"] = {
        capability: sorted({"recall", "usage", "composition", "selection", "transfer", "tradeoff", "edge"} -
                           {row["dimension"] for row in context["mastery"] if row["capability_id"] == capability})
        for capability in sorted(pack["capability_ids"])
    }
    complete = completed_ids(db)
    open_items = [{"id": item["id"], "type": item["type"], "difficulty": item["difficulty"],
                   "capabilities": item["capabilities"]} for item in discover(root, pack)
                  if item["id"] not in complete and item.get("status") != "completed"]
    curriculum = {"concepts": pack["concepts"], "capabilities": pack["capabilities"]}
    prompt = "\n\n".join([
        (root / "prompts" / "generate.md").read_text(),
        (root / "prompts" / f"generate-{kind}.md").read_text(),
        generation_contract(exercise_id, kind, order, path.relative_to(root), pack["snapshot_id"]),
        "ACTIVE SNAPSHOT MANIFEST:\n" + yaml.safe_dump(pack["manifest"], sort_keys=False),
        "CURRICULUM MAP (inspect referenced local snapshot files as needed):\n" + yaml.safe_dump(curriculum, sort_keys=False),
        "LEARNER EVIDENCE:\n" + json.dumps(context, indent=2),
        "OPEN EXERCISES:\n" + json.dumps(open_items, indent=2),
    ])
    before = _files(root)
    (codex or Codex(root)).generate(prompt)
    after = _files(root)
    changed = sorted(str(item.relative_to(root)) for item, digest in before.items() if after.get(item) != digest)
    new_files = set(after) - set(before)
    allowed = bool(new_files) and all(item == path or _inside(item, path) for item in new_files)
    root_shape = path.is_file() if kind == "flash" else path.is_dir()
    if changed or not allowed or not root_shape:
        if path.exists():
            _remove(path)
        outside = sorted(str(item.relative_to(root)) for item in new_files if item != path and not _inside(item, path))
        for item in sorted((item for item in new_files if item.exists() and item != path and not _inside(item, path)), key=lambda p: len(p.parts), reverse=True):
            _remove(item)
        raise RuntimeError(f"generation violated one-root boundary (changed={changed}, outside={outside})")
    try:
        exercise = read_exercise(path, pack)
        if (exercise["id"], exercise["type"], exercise["order"], exercise["snapshot"]) != (exercise_id, kind, order, pack["snapshot_id"]):
            raise ValueError("generated exercise metadata does not match its allocation")
    except (OSError, ValueError):
        _remove(path)
        raise
    return exercise


def _bounded(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else "… output truncated …\n" + text[-limit:]


def _read_targets(exercise, validator: dict) -> str:
    targets = validator.get("targets") or ([exercise.path.name] if exercise.path.is_file() else [])
    if rubric := validator.get("rubric"):
        targets.append(rubric)
    parts = []
    for relative in targets:
        path = exercise.path if exercise.path.is_file() and relative == exercise.path.name else exercise.path / relative
        if not path.is_file() or not _inside(path.resolve(), exercise.path.resolve() if exercise.path.is_dir() else exercise.path.parent.resolve()):
            raise ValueError(f"{exercise['id']}: invalid judge target {relative}")
        try:
            parts.append(f"--- {relative} ---\n{path.read_text()}")
        except UnicodeDecodeError:
            raise ValueError(f"{exercise['id']}: judge target {relative} is not text") from None
    if not parts:
        raise ValueError(f"{exercise['id']}: LLM validator requires targets for a directory exercise")
    return _bounded("\n\n".join(parts), 200_000)


def _judge_prompt(root: Path, exercise, validator: dict, failure_output: str | None = None) -> str:
    purpose = "Classify the deterministic failure without giving solution code." if failure_output is not None else "Judge the learner work."
    material = f"DETERMINISTIC FAILURE:\n{failure_output}" if failure_output is not None else "LEARNER MATERIAL:\n" + _read_targets(exercise, validator)
    return "\n\n".join([(root / "prompts" / "judge.md").read_text(), purpose, material,
        "METADATA:\n" + yaml.safe_dump(exercise.metadata, sort_keys=False)])


def _generic_failure(exercise, summary: str) -> dict:
    observations = declared_observations(exercise, "failed")
    for observation in observations:
        observation["failure_modes"] = ["deterministic_check_failed"]
    return {"passed": False, "score": 0, "summary": summary,
            "capability_observations": observations, "failure_modes": ["deterministic_check_failed"]}


def _command(root: Path, exercise, validator: dict, codex) -> dict:
    missing = [name for name in validator.get("requires_env", []) if not os.environ.get(name)]
    if missing:
        return _generic_failure(exercise, "Missing environment:\n  " + "\n  ".join(missing))
    base = exercise.path if exercise.path.is_dir() else exercise.path.parent
    cwd = (base / validator.get("cwd", ".")).resolve()
    if not _inside(cwd, base.resolve()) or not cwd.is_dir():
        raise ValueError(f"{exercise['id']}: validator cwd escapes or does not exist")
    try:
        completed = subprocess.run(validator["command"], cwd=cwd, text=True, capture_output=True,
                                   timeout=validator.get("timeout_seconds", 120))
        output = _bounded((completed.stdout + completed.stderr).strip())
    except subprocess.TimeoutExpired as error:
        output = _bounded(((error.stdout or "") + (error.stderr or "")) if isinstance(error.stdout, str) else "")
        return _generic_failure(exercise, f"Validation timed out after {validator.get('timeout_seconds', 120)} seconds.\n{output}".strip())
    if completed.returncode:
        generic = _generic_failure(exercise, output or f"Validation command exited {completed.returncode}.")
        if validator.get("classify_failure", True) and codex:
            try:
                classified = codex.judge(_judge_prompt(root, exercise, validator, output))
                if classified.get("capability_observations"):
                    classified["passed"] = False
                    classified["score"] = min(float(classified.get("score", 0)), 0.99)
                    return classified
            except Exception:
                pass
        return generic
    return {"passed": True, "score": 1, "summary": output or "Deterministic check passed.",
            "capability_observations": declared_observations(exercise), "failure_modes": []}


def validate(root: Path, exercise, codex: Codex | None = None) -> dict:
    judge = codex or Codex(root)
    results = []
    for validator in exercise.validators:
        result = _command(root, exercise, validator, judge) if validator["type"] == "command" else judge.judge(_judge_prompt(root, exercise, validator))
        results.append(result)
        if not result.get("passed"):
            break
    observations = [item for result in results for item in result.get("capability_observations", [])]
    failures = [item for result in results for item in result.get("failure_modes", [])]
    return {"passed": bool(results) and all(result.get("passed") for result in results),
            "score": min((float(result.get("score", 0)) for result in results), default=0),
            "summary": "\n".join(result.get("summary", "") for result in results if result.get("summary")),
            "capability_observations": observations, "failure_modes": failures}


def check(root: Path, codex: Codex | None = None):
    pack = preflight(root)
    db = connect(root)
    complete = completed_ids(db)
    results = []
    for exercise in discover(root, pack):
        if exercise["id"] in complete or exercise.get("status") == "completed":
            continue
        result = validate(root, exercise, codex)
        record(db, exercise, result)
        results.append((exercise, result))
        if not result["passed"]:
            break
        complete.add(exercise["id"])
    return results


def status(root: Path) -> dict:
    try:
        pack, errors = preflight(root), []
    except ValueError as error:
        return {"pack_valid": False, "pack_errors": str(error).splitlines()[2:] or [str(error)]}
    db = connect(root)
    exercises = discover(root, pack)
    complete = completed_ids(db) | {item["id"] for item in exercises if item.get("status") == "completed"}
    context = mastery_context(db)
    encountered = {row["capability_id"] for row in context["mastery"]}
    attempted = {row[0] for row in db.execute("SELECT DISTINCT exercise_id FROM attempts")}
    concepts_encountered = {concept["id"] for item in exercises if item["id"] in attempted for concept in item.get("concepts", [])}
    weak = sorted(context["mastery"], key=lambda row: (row["successes"] / row["exposures"], -row["failures"]))[:8]
    return {"pack_valid": True, "pack_errors": [], "product": pack["product"],
        "concepts_total": len(pack["concepts"]), "concepts_encountered": len(concepts_encountered),
        "capabilities_total": len(pack["capabilities"]), "capabilities_encountered": len(encountered),
        "open": [item["id"] for item in exercises if item["id"] not in complete],
        "completed": {kind: sum(item["id"] in complete and item["type"] == kind for item in exercises) for kind in TYPES},
        "weak": weak, "recurring_failures": context["recurring_failures"][:8], "edges": context["edge_evidence"]}
