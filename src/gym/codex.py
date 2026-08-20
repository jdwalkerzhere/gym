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
        try:
            completed = subprocess.run([*command, prompt], cwd=self.root, text=True, capture_output=True)
            if completed.returncode:
                raise RuntimeError(f"Codex failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}")
            return json.loads(Path(output.name).read_text()) if output else None
        finally:
            for temporary in (output, schema):
                if temporary:
                    Path(temporary.name).unlink(missing_ok=True)

    def generate(self, prompt: str) -> None:
        self.run(prompt)

    def judge(self, prompt: str) -> dict:
        observation_properties = {
            "capability_id": {"type": "string"},
            "result": {"type": "string", "enum": ["success", "partial", "failed"]},
            "dimension": {"type": "string", "enum": ["recognition", "recall", "basic", "usage", "composition", "selection", "transfer", "tradeoff", "edge"]},
            "score": {"type": ["number", "null"]},
            "weight": {"type": ["number", "null"]},
            "failure_modes": {"type": ["array", "null"], "items": {"type": "string"}},
            "edge_case": {"type": ["string", "null"]},
            "related_capability": {"type": ["string", "null"]},
        }
        schema = {
            "type": "object", "additionalProperties": False,
            "required": ["passed", "score", "summary", "capability_observations", "failure_modes"],
            "properties": {
                "passed": {"type": "boolean"}, "score": {"type": "number"}, "summary": {"type": "string"},
                "capability_observations": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": list(observation_properties), "properties": observation_properties,
                }},
                "failure_modes": {"type": "array", "items": {"type": "string"}},
            },
        }
        result = self.run(prompt, schema) or {}
        for observation in result.get("capability_observations", []):
            for key in tuple(observation):
                if observation[key] is None:
                    del observation[key]
        return result
