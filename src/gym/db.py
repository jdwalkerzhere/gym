from __future__ import annotations

import json
from pathlib import Path
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
 id INTEGER PRIMARY KEY, exercise_id TEXT NOT NULL, attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 passed INTEGER NOT NULL, score REAL NOT NULL, summary TEXT NOT NULL, result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES attempts(id), capability_id TEXT NOT NULL,
 exercise_type TEXT NOT NULL, result TEXT NOT NULL, dimension TEXT NOT NULL DEFAULT 'basic',
 failure_mode TEXT, edge_case TEXT, related_capability TEXT
);
"""


def connect(root: Path) -> sqlite3.Connection:
    state = root / ".gym"
    state.mkdir(exist_ok=True)
    db = sqlite3.connect(state / "mastery.sqlite")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def record(db: sqlite3.Connection, exercise: dict, result: dict) -> None:
    cursor = db.execute(
        "INSERT INTO attempts(exercise_id, passed, score, summary, result_json) VALUES (?, ?, ?, ?, ?)",
        (exercise["id"], bool(result["passed"]), float(result["score"]), result.get("summary", ""), json.dumps(result)),
    )
    observations = result.get("capability_observations") or [
        {"capability_id": item["id"], "result": "success" if result["passed"] else "failed"}
        for item in exercise["capabilities"]
    ]
    shared_failures = result.get("failure_modes", []) or [None]
    for observation in observations:
        failures = observation.get("failure_modes", shared_failures) or [None]
        for failure in failures:
            db.execute(
                "INSERT INTO observations(attempt_id, capability_id, exercise_type, result, dimension, failure_mode, edge_case, related_capability) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cursor.lastrowid, observation["capability_id"], exercise["type"], observation.get("result", "unknown"), observation.get("dimension", "basic"), failure, observation.get("edge_case"), observation.get("related_capability")),
            )
    db.commit()


def mastery_context(db: sqlite3.Connection) -> dict:
    rows = db.execute("""SELECT capability_id, exercise_type, dimension, COUNT(*) exposures,
        SUM(result = 'success') successes, SUM(result != 'success') failures, MAX(a.attempted_at) last_seen
        FROM observations o JOIN attempts a ON a.id=o.attempt_id GROUP BY capability_id, exercise_type, dimension""").fetchall()
    failures = db.execute("""SELECT capability_id, failure_mode, COUNT(*) count FROM observations
        WHERE failure_mode IS NOT NULL GROUP BY capability_id, failure_mode ORDER BY count DESC""").fetchall()
    return {"mastery": [dict(row) for row in rows], "recurring_failures": [dict(row) for row in failures]}
