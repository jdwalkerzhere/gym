from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import yaml

from .codex import Codex
from .db import connect, mastery_context, record
from .exercises import TYPES, discover, generation_contract, mark_completed, next_identity, read_metadata


def _snapshot(root: Path) -> str:
    product = yaml.safe_load((root / "product" / "product.yaml").read_text())
    return str(product["snapshot"]["id"])


def _files(root: Path) -> dict[Path, str]:
    return {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (root / "exercises").rglob("*") if path.is_file()}


def generate(root: Path, kind: str, codex: Codex | None = None) -> dict:
    if kind not in TYPES:
        raise ValueError(f"unknown exercise type: {kind}")
    exercise_id, order, path = next_identity(root, kind)
    before = _files(root)
    db = connect(root)
    context = mastery_context(db)
    curriculum = {}
    for name in ("concepts", "capabilities", "terminology"):
        source = root / "product" / "knowledge" / f"{name}.yaml"
        curriculum[name] = yaml.safe_load(source.read_text()) if source.exists() else []
    open_items = [{"id": item["id"], "type": item["type"], "capabilities": item["capabilities"]} for item in discover(root) if item["status"] == "open"]
    prompt = "\n\n".join([
        (root / "prompts" / "generate.md").read_text(),
        (root / "prompts" / f"generate-{kind}.md").read_text(),
        generation_contract(exercise_id, kind, order, path.relative_to(root), _snapshot(root)),
        "CURRICULUM:\n" + yaml.safe_dump(curriculum, sort_keys=False),
        "LEARNER STATE:\n" + json.dumps(context, indent=2),
        "OPEN EXERCISES:\n" + json.dumps(open_items, indent=2),
    ])
    (codex or Codex(root)).generate(prompt)
    after = _files(root)
    changed_existing = [item for item in before if after.get(item) != before[item]]
    new_files = set(after) - set(before)
    if changed_existing or new_files != {path}:
        raise RuntimeError(f"generation violated append-only boundary (changed={changed_existing}, new={sorted(map(str, new_files))})")
    try:
        metadata = read_metadata(path)
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise
    if (metadata["id"], metadata["type"], metadata["order"], metadata["snapshot"]) != (exercise_id, kind, order, _snapshot(root)):
        path.unlink()
        raise ValueError("generated exercise metadata does not match its allocation")
    return metadata


def _judge_prompt(root: Path, exercise: dict) -> str:
    path = exercise["path"]
    source = path.read_text() if path.is_file() else "\n\n".join(item.read_text() for item in sorted(path.rglob("*")) if item.is_file())
    return "\n\n".join([(root / "prompts" / "judge.md").read_text(), "EXERCISE AND LEARNER WORK:\n" + source, "METADATA:\n" + yaml.safe_dump({k: v for k, v in exercise.items() if k != "path"}, sort_keys=False)])


def validate(root: Path, exercise: dict, codex: Codex | None = None) -> dict:
    validator = exercise["validator"]
    if validator["type"] in {"command", "hybrid"}:
        command = validator.get("command")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValueError(f"{exercise['id']}: command validator requires a string list")
        cwd = exercise["path"] if exercise["path"].is_dir() else exercise["path"].parent
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
        if completed.returncode:
            return {"passed": False, "score": 0, "summary": (completed.stdout + completed.stderr).strip() or "Validation command failed.", "capability_observations": [], "failure_modes": ["deterministic_check_failed"]}
        if validator["type"] == "command":
            return {"passed": True, "score": 1, "summary": "Deterministic check passed.", "capability_observations": [], "failure_modes": []}
    return (codex or Codex(root)).judge(_judge_prompt(root, exercise))


def check(root: Path, codex: Codex | None = None) -> list[tuple[dict, dict]]:
    db = connect(root)
    results = []
    for exercise in (item for item in discover(root) if item["status"] == "open"):
        result = validate(root, exercise, codex)
        record(db, exercise, result)
        results.append((exercise, result))
        if not result["passed"]:
            break
        mark_completed(exercise)
    return results


def status(root: Path) -> dict:
    db = connect(root)
    exercises = discover(root)
    concepts_file = root / "product" / "knowledge" / "concepts.yaml"
    capabilities_file = root / "product" / "knowledge" / "capabilities.yaml"
    concepts = yaml.safe_load(concepts_file.read_text()) or [] if concepts_file.exists() else []
    capabilities = yaml.safe_load(capabilities_file.read_text()) or [] if capabilities_file.exists() else []
    context = mastery_context(db)
    encountered = {row["capability_id"] for row in context["mastery"]}
    attempted = {row[0] for row in db.execute("SELECT DISTINCT exercise_id FROM attempts")}
    concepts_encountered = {concept["id"] for item in exercises if item["id"] in attempted for concept in item.get("concepts", [])}
    weak = sorted(context["mastery"], key=lambda row: (row["successes"] / row["exposures"], -row["failures"]))[:5]
    return {
        "product": yaml.safe_load((root / "product" / "product.yaml").read_text()),
        "concepts_total": len(concepts), "concepts_encountered": len(concepts_encountered),
        "capabilities_total": len(capabilities), "capabilities_encountered": len(encountered),
        "open": [item["id"] for item in exercises if item["status"] == "open"],
        "completed": {kind: sum(item["status"] == "completed" and item["type"] == kind for item in exercises) for kind in TYPES},
        "weak": weak, "recurring_failures": context["recurring_failures"][:5],
    }
