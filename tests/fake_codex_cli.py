"""Subprocess fake for manual/adapter smoke tests; never calls a model."""

from pathlib import Path
import json
import os
import re
import sys

args = sys.argv[1:]
prompt = args[-1]
if log := os.environ.get("GYM_FAKE_LOG"):
    Path(log).write_text(prompt)

if "EXERCISE AND LEARNER WORK:" in prompt:
    passed = "WRONG" not in prompt
    result = {
        "passed": passed,
        "score": 1 if passed else 0.4,
        "summary": "Correct." if passed else "The answer shows a semantic confusion.",
        "capability_observations": [{"capability_id": "parcel.send", "result": "success" if passed else "failed", "dimension": "usage", "failure_modes": [] if passed else ["semantic_confusion"]}],
        "failure_modes": [] if passed else ["semantic_confusion"],
    }
    Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result))
else:
    relative = re.search(r"at (exercises/\S+)", prompt).group(1).rstrip(".")
    exercise_id = re.search(r"  id: (\S+)", prompt).group(1)
    kind = re.search(r"  type: (\S+)", prompt).group(1)
    order = re.search(r"  order: (\d+)", prompt).group(1)
    snapshot = re.search(r"  snapshot: (\S+)", prompt).group(1)
    body = "WRONG" if kind == "leet" else "ANSWER"
    Path(relative).write_text(f"""---
gym:
  id: {exercise_id}
  type: {kind}
  created_at: 2026-08-18T00:00:00Z
  order: {order}
  snapshot: {snapshot}
  status: open
  capabilities: [{{id: parcel.send, weight: 1.0}}]
  difficulty: 1
  selection: {{reason: new_surface, detail: parcel.send needs practice}}
  validator: {{type: llm}}
  source_refs: [product/snapshot/docs.md]
---
# Exercise

{body}
""")
