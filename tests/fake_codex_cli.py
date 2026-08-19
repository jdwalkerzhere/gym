"""Subprocess fake for manual adapter smoke tests; never calls a model."""

from pathlib import Path
import json
import os
import re
import sys
import yaml

args = sys.argv[1:]
prompt = args[-1]
if log := os.environ.get("GYM_FAKE_LOG"):
    Path(log).write_text(prompt)

if "LEARNER MATERIAL:" in prompt or "DETERMINISTIC FAILURE:" in prompt:
    failed = "DETERMINISTIC FAILURE:" in prompt
    result = {
        "passed": not failed,
        "score": 0.4 if failed else 1,
        "summary": "Classified boundary error." if failed else "Correct.",
        "capability_observations": [{"capability_id": "parcel.send", "result": "failed" if failed else "success", "dimension": "edge" if failed else "recall", "failure_modes": ["boundary_error"] if failed else [], "edge_case": "empty_batch" if failed else None}],
        "failure_modes": ["boundary_error"] if failed else [],
    }
    Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result))
else:
    relative = re.search(r"ALLOCATED EXERCISE ROOT: (\S+)", prompt).group(1)
    exercise_id = re.search(r"  id: (\S+)", prompt).group(1)
    kind = re.search(r"  type: (\S+)", prompt).group(1)
    order = int(re.search(r"  order: (\d+)", prompt).group(1))
    snapshot = re.search(r"  snapshot: (\S+)", prompt).group(1)
    target = Path(relative)
    demonstrates = {"recall": 1.0} if kind == "flash" else {"usage": 1.0, "edge": 0.5} if kind == "leet" else {"selection": 1.0, "tradeoff": 0.5} if kind == "spec" else {"transfer": 1.0, "tradeoff": 0.8}
    validators = [{"type": "llm", "targets": [target.name]}] if kind == "flash" else [{"type": "command", "command": [sys.executable, "grader/check.py"], "timeout_seconds": 10}]
    gym = {"schema_version": 2, "id": exercise_id, "type": kind, "created_at": "2026-08-18T00:00:00Z", "order": order,
           "snapshot": snapshot, "capabilities": [{"id": "parcel.send", "weight": 1.0, "demonstrates": demonstrates}],
           "concepts": [{"id": "delivery"}], "difficulty": order, "selection": {"reason": "new_surface", "detail": "fixture coverage"},
           "source_refs": ["docs-core"], "validators": validators}
    if kind == "flash":
        target.write_text("---\n" + yaml.safe_dump({"gym": gym}, sort_keys=False) + "---\n# Flash\n\nANSWER\n")
    else:
        target.mkdir()
        (target / "exercise.yaml").write_text(yaml.safe_dump({"gym": gym}, sort_keys=False))
        (target / "README.md").write_text(f"# {kind.title()} exercise\n")
        (target / "work").mkdir()
        (target / "work" / "answer.txt").write_text("TODO\n" if kind == "leet" else "PASS\n")
        (target / "grader").mkdir()
        (target / "grader" / "check.py").write_text("from pathlib import Path\nassert Path('work/answer.txt').read_text() == 'PASS\\n'\n")
        if kind == "spec":
            for directory in ("fixtures", "incumbent", "evals"):
                (target / directory).mkdir()
            (target / "fixtures/input.json").write_text("[]\n")
            (target / "incumbent/output.json").write_text("[]\n")
            (target / "evals/rubric.md").write_text("Evaluate requirements and tradeoffs.\n")
        if kind == "engagement":
            for directory in ("client", "facilitator", "evals"):
                (target / directory).mkdir()
            (target / "client/openapi.yaml").write_text("openapi: 3.0.0\n")
            (target / "facilitator/ground-truth.md").write_text("The product may be a poor fit.\n")
            (target / "evals/rubric.md").write_text("Reward discovery and judgment.\n")
