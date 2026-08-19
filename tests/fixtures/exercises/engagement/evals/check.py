from pathlib import Path

for required in ("brief.md", "client/openapi.yaml", "facilitator/ground-truth.md", "work/readout.md", "evals/rubric.md"):
    assert Path(required).exists()
