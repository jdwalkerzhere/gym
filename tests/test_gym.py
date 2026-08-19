from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import sys

import pytest
import yaml

from gym.cli import main
from gym.core import check, generate, status, validate
from gym.db import completed_ids, connect, mastery_context
from gym.exercises import discover, read_exercise
from gym.product import preflight

FIXTURE = Path(__file__).parent / "fixtures" / "fictional-product"
KINDS = ("flash", "leet", "spec", "engagement")


def repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    (tmp_path / "src/gym").mkdir(parents=True)
    (tmp_path / "src/gym/sentinel.py").write_text("VALUE = 1\n")
    shutil.copytree(Path(__file__).parents[1] / "prompts", tmp_path / "prompts")
    for kind in KINDS:
        (tmp_path / "exercises" / kind).mkdir(parents=True)
    (tmp_path / "product" / "knowledge").mkdir(parents=True)
    (tmp_path / "product" / "snapshot").mkdir()
    shutil.copy(FIXTURE / "product.yaml", tmp_path / "product" / "product.yaml")
    for name in ("concepts.yaml", "capabilities.yaml", "terminology.yaml"):
        shutil.copy(FIXTURE / name, tmp_path / "product" / "knowledge" / name)
    for name in ("manifest.yaml", "docs.md", "sdk.py", "openapi.yaml"):
        shutil.copy(FIXTURE / name, tmp_path / "product" / "snapshot" / name)
    shutil.copytree(FIXTURE / "examples", tmp_path / "product" / "snapshot" / "examples")
    return tmp_path


def metadata(kind="flash", number=1, capabilities=None, validators=None, **updates):
    data = {
        "schema_version": 2, "id": f"{kind}-{number:04d}", "type": kind,
        "created_at": "2026-01-01T00:00:00Z", "order": number, "snapshot": "parcelbox-v1",
        "capabilities": capabilities or [{"id": "parcel.send", "weight": 1.0, "demonstrates": {"recall" if kind == "flash" else "usage": 1.0}}],
        "concepts": [{"id": "delivery"}], "difficulty": number,
        "selection": {"reason": "new_surface", "detail": "test"}, "source_refs": ["docs-core"],
        "validators": validators or [{"type": "llm", "targets": ["README.md"]}],
    }
    data.update(updates)
    return data


def standalone(root, number=1, body="ANSWER", **updates):
    gym = metadata("flash", number, **updates)
    path = root / "exercises" / "flash" / f"{number:04d}-exercise.md"
    path.write_text("---\n" + yaml.safe_dump({"gym": gym}, sort_keys=False) + "---\n" + body + "\n")
    return path


def bundle(root, kind="leet", number=2, body="ANSWER", **updates):
    path = root / "exercises" / kind / f"{number:04d}-exercise"
    path.mkdir()
    gym = metadata(kind, number, **updates)
    (path / "exercise.yaml").write_text(yaml.safe_dump({"gym": gym}, sort_keys=False))
    (path / "README.md").write_text(body)
    return path


class FakeCodex:
    def __init__(self, root: Path, shape=None, mutation=None, judge_result=None, judge_error=None):
        self.root, self.shape, self.mutation = root, shape, mutation
        self.judge_result, self.judge_error, self.prompts = judge_result, judge_error, []

    def generate(self, prompt):
        self.prompts.append(prompt)
        relative = re.search(r"ALLOCATED EXERCISE ROOT: (\S+)", prompt).group(1)
        target = self.root / relative
        exercise_id = re.search(r"  id: (\S+)", prompt).group(1)
        kind = re.search(r"  type: (\S+)", prompt).group(1)
        order = int(re.search(r"  order: (\d+)", prompt).group(1))
        gym = metadata(kind, order, id=exercise_id, validators=[{"type": "llm", "targets": ["README.md"]}])
        if kind == "flash" or self.shape == "file":
            target.write_text("---\n" + yaml.safe_dump({"gym": gym}, sort_keys=False) + "---\nANSWER\n")
        else:
            target.mkdir()
            (target / "exercise.yaml").write_text(yaml.safe_dump({"gym": gym}, sort_keys=False))
            (target / "README.md").write_text("Task\n")
            (target / "fixtures").mkdir()
            (target / "fixtures" / "records.json").write_text("[]\n")
        if self.mutation == "existing":
            next(path for path in (self.root / "exercises").rglob("*.md") if path != target).write_text("changed")
        elif self.mutation == "product":
            (self.root / "product" / "product.yaml").write_text("changed")
        elif self.mutation == "source":
            (self.root / "product" / "snapshot" / "docs.md").write_text("changed")
        elif self.mutation == "application":
            (self.root / "src/gym/sentinel.py").write_text("changed")
        elif self.mutation == "state":
            (self.root / ".gym" / "intrusion").write_text("changed")
        elif self.mutation == "outside":
            (self.root / "stray.txt").write_text("stray")
        elif self.mutation == "two_roots":
            other = target.parent / "9999-other"
            other.mkdir()
            (other / "x").write_text("x")

    def judge(self, prompt):
        self.prompts.append(prompt)
        if self.judge_error:
            raise self.judge_error
        return copy.deepcopy(self.judge_result or {"passed": True, "score": 1, "summary": "ok", "capability_observations": [{"capability_id": "parcel.send", "result": "success", "dimension": "recall", "weight": 1.0}], "failure_modes": []})


def test_pack_preflight_and_integrity_failures(tmp_path):
    root = repo(tmp_path)
    assert preflight(root)["source_ids"] == {"docs-core", "sdk-client", "api-spec", "examples-repository"}
    cases = [
        ("missing local path", lambda: (root / "product/snapshot/docs.md").unlink()),
        ("unknown prerequisite", lambda: _edit_yaml(root / "product/knowledge/capabilities.yaml", lambda x: x[0].update(prerequisites=["missing"]))),
        ("duplicate", lambda: _edit_yaml(root / "product/knowledge/capabilities.yaml", lambda x: x.append(copy.deepcopy(x[0])))),
        ("does not match", lambda: _edit_yaml(root / "product/snapshot/manifest.yaml", lambda x: x["snapshot"].update(id="other"))),
    ]
    for message, mutate in cases:
        case = repo(tmp_path / message.replace(" ", "-"))
        root = case
        mutate()
        with pytest.raises(ValueError, match=message):
            preflight(root)


def _edit_yaml(path, change):
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_standalone_directory_sidecar_and_metadata_validation(tmp_path):
    root = repo(tmp_path)
    pack = preflight(root)
    assert read_exercise(standalone(root), pack)["id"] == "flash-0001"
    assert read_exercise(bundle(root), pack)["id"] == "leet-0002"
    code = root / "exercises/flash/0003-fix.py"
    code.write_text("pass\n")
    sidecar = code.with_name(code.name + ".exercise.yaml")
    sidecar.write_text(yaml.safe_dump({"gym": metadata("flash", 3)}, sort_keys=False))
    assert read_exercise(sidecar, pack).path == code
    variants = [
        ("unknown capabilities", {"capabilities": [{"id": "bad", "weight": 1, "demonstrates": {"recall": 1}}]}),
        ("unknown concepts", {"concepts": [{"id": "bad"}]}),
        ("missing gym fields: snapshot", {"snapshot": None}),
        ("not active snapshot", {"snapshot": "old"}),
        ("source_refs are required", {"source_refs": []}),
        ("unresolved source refs", {"source_refs": ["missing"]}),
        ("command validator requires", {"validators": [{"type": "command", "command": "pytest"}]}),
        ("needs demonstrates", {"capabilities": [{"id": "parcel.send", "weight": 1}]}),
    ]
    for index, (message, updates) in enumerate(variants, 10):
        path = standalone(root, index, **updates)
        if "snapshot" in updates and updates["snapshot"] is None:
            data = yaml.safe_load(re.match(r"---\n(.*?)---\n", path.read_text(), re.S).group(1)); del data["gym"]["snapshot"]
            path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n")
        with pytest.raises(ValueError, match=message):
            read_exercise(path, pack)


def test_duplicate_id_and_order_rejected(tmp_path):
    root = repo(tmp_path)
    standalone(root, 1)
    bundle(root, "leet", 2, id="flash-0001", order=2)
    with pytest.raises(ValueError, match="duplicate exercise id"):
        discover(root, preflight(root))
    shutil.rmtree(root / "exercises/leet/0002-exercise")
    bundle(root, "leet", 2, order=1)
    with pytest.raises(ValueError, match="duplicate exercise creation order"):
        discover(root, preflight(root))


def test_generation_accepts_one_file_or_directory_root(tmp_path):
    root = repo(tmp_path)
    flash = generate(root, "flash", FakeCodex(root))
    leet = generate(root, "leet", FakeCodex(root))
    assert flash.path.is_file()
    assert leet.path.is_dir() and (leet.path / "fixtures/records.json").exists()
    assert len(discover(root, preflight(root))) == 2


@pytest.mark.parametrize("mutation", ["existing", "product", "source", "application", "state", "outside", "two_roots"])
def test_generation_rejects_mutation_outside_allocated_root(tmp_path, mutation):
    root = repo(tmp_path)
    if mutation == "existing":
        standalone(root, 1)
    with pytest.raises(RuntimeError, match="one-root boundary"):
        generate(root, "leet", FakeCodex(root, mutation=mutation))


def command_validator(**updates):
    value = {"type": "command", "command": [sys.executable, "-c", "print('ok')"], "timeout_seconds": 5, "classify_failure": False}
    value.update(updates)
    return value


def test_command_success_declares_dimensions_difficulty_weights_and_cwd(tmp_path):
    root = repo(tmp_path)
    capabilities = [{"id": "parcel.send", "weight": .6, "demonstrates": {"usage": 1, "composition": .7, "edge": .4}}]
    path = bundle(root, capabilities=capabilities, difficulty=5, validators=[command_validator(cwd="work", command=[sys.executable, "-c", "from pathlib import Path; assert Path('marker').exists()"] )])
    (path / "work").mkdir(); (path / "work/marker").write_text("yes")
    result = check(root, FakeCodex(root))[0][1]
    assert result["passed"]
    rows = connect(root).execute("SELECT dimension, difficulty, weight FROM observations ORDER BY dimension").fetchall()
    assert {row["dimension"] for row in rows} == {"usage", "composition", "edge"}
    assert {row["difficulty"] for row in rows} == {5}
    assert {round(row["weight"], 2) for row in rows} == {.6, .42, .24}


def test_command_failure_timeout_missing_env_and_classifier_fallback(tmp_path, monkeypatch):
    root = repo(tmp_path)
    failures = [
        command_validator(command=[sys.executable, "-c", "raise SystemExit(2)"]),
        command_validator(command=[sys.executable, "-c", "import time; time.sleep(1)"], timeout_seconds=.01),
        command_validator(requires_env=["GYM_TEST_MISSING"]),
    ]
    monkeypatch.delenv("GYM_TEST_MISSING", raising=False)
    for number, validator in enumerate(failures, 1):
        path = bundle(root, "leet", number, validators=[validator])
        result = validate(root, read_exercise(path, preflight(root)), FakeCodex(root, judge_error=RuntimeError("offline")))
        assert not result["passed"] and result["capability_observations"]
        shutil.rmtree(path)
    assert "timed out" in validate(root, read_exercise(bundle(root, "leet", 8, validators=[failures[1]]), preflight(root)), FakeCodex(root))["summary"]
    assert "Missing environment" in validate(root, read_exercise(bundle(root, "leet", 9, validators=[failures[2]]), preflight(root)), FakeCodex(root))["summary"]


def test_llm_and_hybrid_merge_observations(tmp_path):
    root = repo(tmp_path)
    llm = {"passed": True, "score": .8, "summary": "rubric passed", "capability_observations": [{"capability_id": "parcel.send", "result": "success", "dimension": "tradeoff", "weight": .5}], "failure_modes": []}
    path = bundle(root, validators=[command_validator(), {"type": "llm", "targets": ["README.md"]}])
    result = validate(root, read_exercise(path, preflight(root)), FakeCodex(root, judge_result=llm))
    assert result["passed"] and result["score"] == .8
    assert {item["dimension"] for item in result["capability_observations"]} == {"usage", "tradeoff"}


def test_mixed_roots_stop_then_resume_and_keep_files_immutable(tmp_path):
    root = repo(tmp_path)
    flash = standalone(root, 1, validators=[command_validator()])
    leet = bundle(root, "leet", 2, validators=[command_validator(command=[sys.executable, "-c", "from pathlib import Path; assert Path('work.py').read_text() == 'PASS\\n'"])])
    (leet / "work.py").write_text("TODO\n")
    spec = bundle(root, "spec", 3, validators=[command_validator()])
    results = check(root, FakeCodex(root))
    assert [item["id"] for item, _ in results] == ["flash-0001", "leet-0002"]
    assert completed_ids(connect(root)) == {"flash-0001"}
    assert flash.read_text().endswith("\n") and "completed" not in flash.read_text()
    assert "spec-0003" not in {row[0] for row in connect(root).execute("SELECT exercise_id FROM attempts")}
    (leet / "work.py").write_text("PASS\n")
    assert [item["id"] for item, _ in check(root, FakeCodex(root))] == ["leet-0002", "spec-0003"]
    assert completed_ids(connect(root)) == {"flash-0001", "leet-0002", "spec-0003"}


def test_failure_confusion_history_depth_and_generation_context(tmp_path):
    root = repo(tmp_path)
    failed = {"passed": False, "score": .4, "summary": "confused", "capability_observations": [{"capability_id": "parcel.send", "result": "failed", "dimension": "composition", "failure_modes": ["confused_operation"], "related_capability": "parcel.track", "edge_case": "empty_batch"}], "failure_modes": ["confused_operation"]}
    path = bundle(root, "leet", 1)
    judge = FakeCodex(root, judge_result=failed)
    check(root, judge); check(root, judge)
    context = mastery_context(connect(root))
    assert context["recurring_failures"][0]["count"] == 2
    assert context["recurring_failures"][0]["related_capability"] == "parcel.track"
    generator = FakeCodex(root)
    generate(root, "engagement", generator)
    prompt = generator.prompts[-1]
    assert '"dimension": "composition"' in prompt and '"highest_attempted_difficulty": 1.0' in prompt
    assert "confused_operation" in prompt and "empty_batch" in prompt and "untested_dimensions" in prompt


def test_flash_evidence_does_not_imply_higher_depth(tmp_path):
    root = repo(tmp_path)
    standalone(root, validators=[command_validator()])
    check(root, FakeCodex(root))
    rows = mastery_context(connect(root))["mastery"]
    assert {(row["exercise_type"], row["dimension"]) for row in rows} == {("flash", "recall")}


def test_realistic_leet_spec_and_engagement_bundles(tmp_path):
    root = repo(tmp_path)
    fixtures = Path(__file__).parent / "fixtures" / "exercises"
    leet = root / "exercises/leet/0001-exercise"
    spec = root / "exercises/spec/0002-exercise"
    engagement = root / "exercises/engagement/0003-exercise"
    for source, target in ((fixtures / "leet", leet), (fixtures / "spec", spec), (fixtures / "engagement", engagement)):
        shutil.copytree(source, target)
        _edit_yaml(target / "exercise.yaml", lambda x: x["gym"]["validators"][0]["command"].__setitem__(0, sys.executable))
    assert not check(root, FakeCodex(root))[0][1]["passed"]
    (leet / "work.py").write_text("def count(items): return len(items)\n")
    resumed = check(root, FakeCodex(root))
    assert all(result["passed"] for _, result in resumed)
    assert [item["id"] for item, _ in resumed] == ["leet-0001", "spec-0002", "engagement-0003"]
    assert all(path.is_dir() for path in (spec, engagement))


def test_status_health_and_cli_remain_thin(monkeypatch, tmp_path, capsys):
    root = repo(tmp_path)
    assert status(root)["pack_valid"]
    (root / "product/snapshot/docs.md").unlink()
    assert not status(root)["pack_valid"]
    monkeypatch.chdir(root)
    assert main(["status"]) == 1
    assert "Product pack: INVALID" in capsys.readouterr().out


def test_existing_v1_database_migrates_additively(tmp_path):
    root = repo(tmp_path)
    state = root / ".gym"; state.mkdir()
    import sqlite3
    db = sqlite3.connect(state / "mastery.sqlite")
    db.executescript("""CREATE TABLE attempts(id INTEGER PRIMARY KEY, exercise_id TEXT, attempted_at TEXT DEFAULT CURRENT_TIMESTAMP, passed INTEGER, score REAL, summary TEXT, result_json TEXT);
    CREATE TABLE observations(id INTEGER PRIMARY KEY, attempt_id INTEGER, capability_id TEXT, exercise_type TEXT, result TEXT, dimension TEXT, failure_mode TEXT, edge_case TEXT, related_capability TEXT);""")
    db.close()
    migrated = connect(root)
    assert {"exercise_id", "score", "difficulty", "weight"} <= {row[1] for row in migrated.execute("PRAGMA table_info(observations)")}
    assert migrated.execute("SELECT name FROM sqlite_master WHERE name='completions'").fetchone()
