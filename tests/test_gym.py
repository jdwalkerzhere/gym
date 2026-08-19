from __future__ import annotations

import re
from pathlib import Path
import sys

import pytest
import yaml

from gym.cli import main
from gym.core import check, generate, status
from gym.db import connect, mastery_context
from gym.exercises import discover


def repo(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    source_prompts = Path(__file__).parents[1] / "prompts"
    for source in source_prompts.glob("*.md"):
        (prompts / source.name).write_text(source.read_text())
    for kind in ("flash", "leet", "spec", "engagement"):
        (tmp_path / "exercises" / kind).mkdir(parents=True)
    knowledge = tmp_path / "product" / "knowledge"
    knowledge.mkdir(parents=True)
    (tmp_path / "product" / "product.yaml").write_text("product:\n  name: Fixture Product\nsnapshot:\n  id: fixture-v1\n")
    (knowledge / "concepts.yaml").write_text("- id: delivery\n  name: Delivery\n")
    (knowledge / "capabilities.yaml").write_text("- id: parcel.send\n  name: Send parcel\n- id: parcel.track\n  name: Track parcel\n")
    (knowledge / "terminology.yaml").write_text("[]\n")
    (tmp_path / "product" / "snapshot").mkdir()
    (tmp_path / "product" / "snapshot" / "docs.md").write_text("Parcels can be sent and tracked.\n")
    return tmp_path


class FakeCodex:
    def __init__(self, root: Path, malformed: bool = False):
        self.root, self.malformed, self.prompts = root, malformed, []

    def generate(self, prompt: str) -> None:
        self.prompts.append(prompt)
        path = re.search(r"at (exercises/\S+)", prompt).group(1)
        exercise_id = re.search(r"  id: (\S+)", prompt).group(1)
        kind = re.search(r"  type: (\S+)", prompt).group(1)
        order = int(re.search(r"  order: (\d+)", prompt).group(1))
        target = self.root / path.rstrip(".")
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.malformed:
            target.write_text("# no metadata\n")
            return
        target.write_text(f"""---
gym:
  id: {exercise_id}
  type: {kind}
  created_at: 2026-01-01T00:00:00Z
  order: {order}
  snapshot: fixture-v1
  status: open
  capabilities:
    - id: parcel.send
      weight: 1.0
  difficulty: 1
  selection:
    reason: new_surface
    detail: parcel.send is unseen
  validator:
    type: llm
  source_refs: [product/snapshot/docs.md]
---
# Exercise

ANSWER
""")

    def judge(self, prompt: str) -> dict:
        passed = "ANSWER" in prompt and "WRONG" not in prompt
        return {"passed": passed, "score": 1 if passed else 0.4, "summary": "ok" if passed else "semantic confusion", "capability_observations": [{"capability_id": "parcel.send", "result": "success" if passed else "failed", "dimension": "usage", "failure_modes": [] if passed else ["semantic_confusion"]}], "failure_modes": [] if passed else ["semantic_confusion"]}


def exercise(root: Path, kind: str, number: int, body: str, capability: str = "parcel.send") -> Path:
    path = root / "exercises" / kind / f"{number:04d}-exercise.md"
    path.write_text(f"""---
gym:
  id: {kind}-{number:04d}
  type: {kind}
  created_at: 2026-01-01T00:00:00Z
  order: {number}
  snapshot: fixture-v1
  status: open
  capabilities: [{{id: {capability}, weight: 1.0}}]
  difficulty: {number}
  selection: {{reason: new_surface}}
  validator:
    type: llm
---
{body}
""")
    return path


def test_generation_is_one_append_only_file_and_receives_mastery(tmp_path):
    root = repo(tmp_path)
    old = exercise(root, "leet", 1, "ANSWER")
    fake = FakeCodex(root)
    check(root, fake)
    original = old.read_text()
    generated = generate(root, "flash", fake)
    assert generated["id"] == "flash-0001"
    assert old.read_text() == original.replace("  status: open", "  status: completed")
    assert len([item for item in discover(root) if item["type"] == "flash"]) == 1
    assert '"capability_id": "parcel.send"' in fake.prompts[-1]
    assert '"exercise_type": "leet"' in fake.prompts[-1]


def test_malformed_generation_is_rejected_and_removed(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        generate(root, "flash", FakeCodex(root, malformed=True))
    assert not list((root / "exercises" / "flash").iterdir())


def test_check_stops_at_first_failure_then_continues_without_moving_files(tmp_path):
    root = repo(tmp_path)
    first = exercise(root, "flash", 1, "ANSWER")
    second = exercise(root, "leet", 2, "WRONG")
    third = exercise(root, "spec", 3, "ANSWER", "parcel.track")
    fake = FakeCodex(root)
    results = check(root, fake)
    assert [item["id"] for item, _ in results] == ["flash-0001", "leet-0002"]
    assert "status: completed" in first.read_text()
    assert "status: open" in second.read_text()
    assert "status: open" in third.read_text()
    assert first.exists() and second.exists() and third.exists()
    context = mastery_context(connect(root))
    assert {row["exercise_type"] for row in context["mastery"]} == {"flash", "leet"}
    assert context["recurring_failures"][0]["failure_mode"] == "semantic_confusion"
    second.write_text(second.read_text().replace("WRONG", "ANSWER"))
    assert [item["id"] for item, _ in check(root, fake)] == ["leet-0002", "spec-0003"]
    assert all(item["status"] == "completed" for item in discover(root))
    assert status(root)["completed"] == {"flash": 1, "leet": 1, "spec": 1, "engagement": 0}


def test_repeated_failures_depth_and_edge_observations_accumulate(tmp_path):
    root = repo(tmp_path)
    item = exercise(root, "engagement", 1, "WRONG")
    fake = FakeCodex(root)
    check(root, fake)
    check(root, fake)
    context = mastery_context(connect(root))
    assert context["recurring_failures"][0]["count"] == 2
    assert context["mastery"][0]["exercise_type"] == "engagement"
    assert context["mastery"][0]["dimension"] == "usage"
    assert item.exists()


def test_edge_and_confusion_observations_remain_structured(tmp_path):
    root = repo(tmp_path)
    exercise(root, "spec", 1, "EDGE")

    class EdgeJudge(FakeCodex):
        def judge(self, prompt):
            return {"passed": False, "score": 0.5, "summary": "boundary missed", "capability_observations": [{"capability_id": "parcel.send", "result": "partial", "dimension": "edge", "failure_modes": ["incomplete_edge_handling"], "edge_case": "empty_parcel", "related_capability": "parcel.track"}], "failure_modes": ["incomplete_edge_handling"]}

    check(root, EdgeJudge(root))
    row = connect(root).execute("SELECT dimension, edge_case, related_capability FROM observations").fetchone()
    assert tuple(row) == ("edge", "empty_parcel", "parcel.track")


def test_cli_dispatches_each_generation_type(monkeypatch, tmp_path):
    root = repo(tmp_path)
    monkeypatch.chdir(root)
    called = []
    monkeypatch.setattr("gym.cli.generate", lambda root, kind: called.append(kind) or {"path": root / "exercises" / kind / "x.md", "capabilities": [{"id": "x"}], "selection": {"reason": "new_surface"}})
    for kind in ("flash", "leet", "spec", "engagement"):
        assert main([kind]) == 0
    assert called == ["flash", "leet", "spec", "engagement"]
