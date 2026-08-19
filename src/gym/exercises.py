from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

import yaml

TYPES = ("flash", "leet", "spec", "engagement")
DIMENSIONS = {"recognition", "recall", "basic", "usage", "composition", "selection", "transfer", "tradeoff", "edge"}
REQUIRED = {"id", "type", "created_at", "order", "snapshot", "capabilities", "difficulty", "selection"}


@dataclass(frozen=True)
class ExerciseRoot:
    path: Path
    metadata_path: Path
    metadata: dict

    def __getitem__(self, key):
        return self.path if key == "path" else self.metadata[key]

    def get(self, key, default=None):
        return self.metadata.get(key, default)

    @property
    def validators(self) -> list[dict]:
        return self.metadata["validators"]


def _load(path: Path) -> tuple[Path, dict]:
    if path.is_dir():
        source = path / "exercise.yaml"
        data = yaml.safe_load(source.read_text())
    elif path.name.endswith(".exercise.yaml"):
        source = path
        data = yaml.safe_load(source.read_text())
        path = path.with_name(path.name.removesuffix(".exercise.yaml"))
        if not path.exists():
            raise ValueError(f"{source}: standalone exercise file is missing")
    else:
        source = path
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", source.read_text(), re.S)
        if not match:
            raise ValueError(f"{source}: missing YAML frontmatter")
        data = yaml.safe_load(match.group(1))
    gym = data.get("gym") if isinstance(data, dict) else None
    if not isinstance(gym, dict):
        raise ValueError(f"{source}: missing gym metadata")
    return source, gym


def read_exercise(path: Path, pack: dict | None = None) -> ExerciseRoot:
    root_path = path.with_name(path.name.removesuffix(".exercise.yaml")) if path.name.endswith(".exercise.yaml") else path
    source, gym = _load(path)
    missing = REQUIRED - set(gym)
    if missing:
        raise ValueError(f"{source}: missing gym fields: {', '.join(sorted(missing))}")
    if gym["type"] not in TYPES or not isinstance(gym["order"], int) or gym["order"] < 1:
        raise ValueError(f"{source}: invalid type or creation order")
    if not isinstance(gym["difficulty"], (int, float)) or gym["difficulty"] <= 0:
        raise ValueError(f"{source}: difficulty must be positive")
    if not isinstance(gym["capabilities"], list) or not gym["capabilities"]:
        raise ValueError(f"{source}: capabilities must be a non-empty list")
    for capability in gym["capabilities"]:
        demonstrates = capability.get("demonstrates")
        if gym.get("schema_version", 1) >= 2 and (not isinstance(demonstrates, dict) or not demonstrates):
            raise ValueError(f"{source}: capability {capability.get('id')} needs demonstrates evidence")
        if demonstrates and (set(demonstrates) - DIMENSIONS or any(not isinstance(v, (int, float)) or not 0 < v <= 1 for v in demonstrates.values())):
            raise ValueError(f"{source}: invalid demonstrates evidence")
        if not isinstance(capability.get("weight", 1), (int, float)) or not 0 < capability.get("weight", 1) <= 1:
            raise ValueError(f"{source}: invalid capability weight")
    validators = gym.get("validators")
    if validators is None and "validator" in gym:  # V1 compatibility
        legacy = gym["validator"]
        validators = ([{"type": "command", **{k: v for k, v in legacy.items() if k not in {"type"}}}, {"type": "llm"}]
                      if legacy.get("type") == "hybrid" else [legacy])
    if not isinstance(validators, list) or not validators:
        raise ValueError(f"{source}: validators must be a non-empty list")
    for validator in validators:
        if not isinstance(validator, dict) or validator.get("type") not in {"command", "llm"}:
            raise ValueError(f"{source}: malformed validator")
        if validator["type"] == "command" and (not isinstance(validator.get("command"), list) or not validator["command"] or not all(isinstance(x, str) for x in validator["command"])):
            raise ValueError(f"{source}: command validator requires an argv list")
        if "timeout_seconds" in validator and (not isinstance(validator["timeout_seconds"], (int, float)) or validator["timeout_seconds"] <= 0):
            raise ValueError(f"{source}: invalid validator timeout")
        if "requires_env" in validator and (not isinstance(validator["requires_env"], list) or not all(isinstance(x, str) for x in validator["requires_env"])):
            raise ValueError(f"{source}: requires_env must be a string list")
    gym = dict(gym, validators=validators)
    if pack:
        if gym["snapshot"] != pack["snapshot_id"]:
            raise ValueError(f"{source}: snapshot {gym['snapshot']} is not active snapshot {pack['snapshot_id']}")
        unknown_caps = {item.get("id") for item in gym["capabilities"]} - pack["capability_ids"]
        unknown_concepts = {item.get("id") for item in gym.get("concepts", [])} - pack["concept_ids"]
        refs = gym.get("source_refs")
        if unknown_caps:
            raise ValueError(f"{source}: unknown capabilities: {', '.join(sorted(unknown_caps))}")
        if unknown_concepts:
            raise ValueError(f"{source}: unknown concepts: {', '.join(sorted(unknown_concepts))}")
        if not refs:
            raise ValueError(f"{source}: source_refs are required")
        unknown_refs = set(refs) - pack["source_ids"]
        if unknown_refs:
            raise ValueError(f"{source}: unresolved source refs: {', '.join(sorted(unknown_refs))}")
    return ExerciseRoot(root_path, source, gym)


def discover(root: Path, pack: dict | None = None) -> list[ExerciseRoot]:
    found = []
    for kind in TYPES:
        directory = root / "exercises" / kind
        if not directory.exists():
            continue
        sidecars = {p.name.removesuffix(".exercise.yaml") for p in directory.glob("*.exercise.yaml")}
        for path in directory.iterdir():
            if path.name.startswith(".") or path.name.endswith(".exercise.yaml"):
                continue
            if path.is_dir() and (path / "exercise.yaml").exists():
                found.append(read_exercise(path, pack))
            elif path.is_file() and (path.suffix == ".md" or path.name in sidecars):
                found.append(read_exercise(path.with_name(path.name + ".exercise.yaml") if path.name in sidecars else path, pack))
    ids = [item["id"] for item in found]
    orders = [item["order"] for item in found]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate exercise id")
    if len(orders) != len(set(orders)):
        raise ValueError("duplicate exercise creation order")
    return sorted(found, key=lambda item: item["order"])


def next_identity(root: Path, kind: str) -> tuple[str, int, Path]:
    exercises = discover(root)
    order = max((item["order"] for item in exercises), default=0) + 1
    sequence = 1 + max((int(item["id"].split("-")[-1]) for item in exercises if item["type"] == kind and item["id"].split("-")[-1].isdigit()), default=0)
    exercise_id = f"{kind}-{sequence:04d}"
    suffix = ".md" if kind == "flash" else ""
    return exercise_id, order, root / "exercises" / kind / f"{sequence:04d}-exercise{suffix}"


def generation_contract(exercise_id: str, kind: str, order: int, path: Path, snapshot: str) -> str:
    directory_note = "Create a directory at this path and put canonical metadata in exercise.yaml." if not path.suffix else "Create this standalone Markdown file with YAML frontmatter."
    return f"""ALLOCATED EXERCISE ROOT: {path}
{directory_note}
Create exactly this one root and any necessary files beneath it; modify nothing outside it.
Canonical `gym` metadata must contain:
  schema_version: 2
  id: {exercise_id}
  type: {kind}
  created_at: {datetime.now(timezone.utc).isoformat()}
  order: {order}
  snapshot: {snapshot}
  capabilities:
    - id: a.real.capability
      weight: 1.0
      demonstrates: {{usage: 1.0}}
  concepts: []
  difficulty: 1
  selection: {{reason: new_surface, detail: concise reason}}
  source_refs: [a-stable-manifest-source-id]
  validators:
    - type: llm
Do not include learner completion status; completion is SQLite learner state.
"""
