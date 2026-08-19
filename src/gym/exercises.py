from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

import yaml

TYPES = ("flash", "leet", "spec", "engagement")
REQUIRED = {"id", "type", "created_at", "order", "snapshot", "status", "capabilities", "difficulty", "selection", "validator"}


def read_metadata(path: Path) -> dict:
    source = path if path.suffix in {".yaml", ".yml"} else path / "exercise.yaml" if path.is_dir() else path
    text = source.read_text()
    if source.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
        if not match:
            raise ValueError(f"{source}: missing YAML frontmatter")
        data = yaml.safe_load(match.group(1))
    gym = data.get("gym") if isinstance(data, dict) else None
    missing = REQUIRED - set(gym or {})
    if missing:
        raise ValueError(f"{source}: missing gym fields: {', '.join(sorted(missing))}")
    if gym["type"] not in TYPES or gym["status"] not in {"open", "completed"}:
        raise ValueError(f"{source}: invalid exercise type or status")
    if not isinstance(gym["capabilities"], list) or not gym["capabilities"]:
        raise ValueError(f"{source}: capabilities must be a non-empty list")
    if gym["validator"].get("type") not in {"command", "llm", "hybrid"}:
        raise ValueError(f"{source}: unsupported validator")
    gym["path"] = path
    return gym


def discover(root: Path) -> list[dict]:
    found = []
    for kind in TYPES:
        directory = root / "exercises" / kind
        if not directory.exists():
            continue
        candidates = [*directory.glob("*.md"), *directory.glob("*.yaml"), *[p for p in directory.iterdir() if p.is_dir() and (p / "exercise.yaml").exists()]]
        found.extend(read_metadata(path) for path in candidates)
    ids = [item["id"] for item in found]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate exercise id")
    return sorted(found, key=lambda item: (item["order"], item["id"]))


def next_identity(root: Path, kind: str) -> tuple[str, int, Path]:
    exercises = discover(root)
    order = max((item["order"] for item in exercises), default=0) + 1
    sequence = 1 + max((int(item["id"].split("-")[-1]) for item in exercises if item["type"] == kind and item["id"].split("-")[-1].isdigit()), default=0)
    exercise_id = f"{kind}-{sequence:04d}"
    return exercise_id, order, root / "exercises" / kind / f"{sequence:04d}-exercise.md"


def mark_completed(metadata: dict) -> None:
    path = metadata["path"]
    source = path / "exercise.yaml" if path.is_dir() else path
    text = source.read_text()
    if source.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
        data["gym"]["status"] = "completed"
        source.write_text(yaml.safe_dump(data, sort_keys=False))
    else:
        source.write_text(text.replace("  status: open", "  status: completed", 1))


def generation_contract(exercise_id: str, kind: str, order: int, path: Path, snapshot: str) -> str:
    return f"""Write exactly one new learner-facing exercise at {path}.
It must use YAML frontmatter with this shape (add source_refs and answer sections as needed):
---
gym:
  id: {exercise_id}
  type: {kind}
  created_at: {datetime.now(timezone.utc).isoformat()}
  order: {order}
  snapshot: {snapshot}
  status: open
  capabilities:
    - id: selected.capability
      weight: 1.0
  concepts: []
  difficulty: 1
  selection:
    reason: new_surface
    detail: concise evidence-based reason
  validator:
    type: llm
---
Do not create a reference answer. Do not modify any other file. Ground product claims in the frozen snapshot.
"""
