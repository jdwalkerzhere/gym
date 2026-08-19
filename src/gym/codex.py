from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


class Codex:
    def __init__(self, root: Path, command: str | None = None):
        self.root = root
        self.command = shlex.split(command or os.environ.get("GYM_CODEX_COMMAND", "codex exec"))

    def run(self, prompt: str, output_schema: dict | None = None) -> dict | None:
        command = [*self.command, "--sandbox", "workspace-write", "--skip-git-repo-check"]
        output = None
        schema = None
        if output_schema:
            output = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
            output.close()
            schema = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            json.dump(output_schema, schema)
            schema.close()
            command += ["--output-schema", schema.name, "--output-last-message", output.name]
        completed = subprocess.run([*command, prompt], cwd=self.root, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(f"Codex failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}")
        return json.loads(Path(output.name).read_text()) if output else None

    def generate(self, prompt: str) -> None:
        self.run(prompt)

    def judge(self, prompt: str) -> dict:
        schema = {
            "type": "object", "additionalProperties": False,
            "required": ["passed", "score", "summary", "capability_observations", "failure_modes"],
            "properties": {
                "passed": {"type": "boolean"}, "score": {"type": "number"}, "summary": {"type": "string"},
                "capability_observations": {"type": "array", "items": {"type": "object"}},
                "failure_modes": {"type": "array", "items": {"type": "string"}},
            },
        }
        return self.run(prompt, schema) or {}
