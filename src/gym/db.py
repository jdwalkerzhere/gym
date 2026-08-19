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
 failure_mode TEXT, edge_case TEXT, related_capability TEXT,
 exercise_id TEXT, score REAL, difficulty REAL, weight REAL
);
CREATE TABLE IF NOT EXISTS completions (
 exercise_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, attempt_id INTEGER NOT NULL REFERENCES attempts(id)
);
"""


def connect(root: Path) -> sqlite3.Connection:
    state = root / ".gym"
    state.mkdir(exist_ok=True)
    db = sqlite3.connect(state / "mastery.sqlite")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    columns = {row[1] for row in db.execute("PRAGMA table_info(observations)")}
    for name, kind in {"exercise_id": "TEXT", "score": "REAL", "difficulty": "REAL", "weight": "REAL"}.items():
        if name not in columns:
            db.execute(f"ALTER TABLE observations ADD COLUMN {name} {kind}")
    db.commit()
    return db


def completed_ids(db: sqlite3.Connection) -> set[str]:
    return {row[0] for row in db.execute("SELECT exercise_id FROM completions")}


def declared_observations(exercise, result: str = "success") -> list[dict]:
    observations = []
    for capability in exercise["capabilities"]:
        demonstrates = capability.get("demonstrates") or {"basic": 1.0}  # V1 exercise compatibility
        for dimension, evidence_weight in demonstrates.items():
            observations.append({
                "capability_id": capability["id"], "result": result, "dimension": dimension,
                "weight": capability.get("weight", 1.0) * evidence_weight,
            })
    return observations


def record(db: sqlite3.Connection, exercise, result: dict) -> None:
    cursor = db.execute(
        "INSERT INTO attempts(exercise_id, passed, score, summary, result_json) VALUES (?, ?, ?, ?, ?)",
        (exercise["id"], bool(result["passed"]), float(result["score"]), result.get("summary", ""), json.dumps(result)),
    )
    observations = result.get("capability_observations")
    if not observations:
        observations = declared_observations(exercise, "success" if result["passed"] else "failed")
    shared_failures = result.get("failure_modes", []) or [None]
    capability_weights = {item["id"]: item.get("weight", 1.0) for item in exercise["capabilities"]}
    for observation in observations:
        failures = observation.get("failure_modes", shared_failures) or [None]
        for failure in failures:
            db.execute(
                """INSERT INTO observations(
                    attempt_id, capability_id, exercise_type, result, dimension, failure_mode,
                    edge_case, related_capability, exercise_id, score, difficulty, weight
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cursor.lastrowid, observation["capability_id"], exercise["type"], observation.get("result", "unknown"),
                 observation.get("dimension", "basic"), failure, observation.get("edge_case"), observation.get("related_capability"),
                 exercise["id"], observation.get("score", result["score"]), exercise["difficulty"],
                 observation.get("weight", capability_weights.get(observation["capability_id"], 1.0))),
            )
    if result["passed"]:
        db.execute("INSERT OR IGNORE INTO completions(exercise_id, attempt_id) VALUES (?, ?)", (exercise["id"], cursor.lastrowid))
    db.commit()


def mastery_context(db: sqlite3.Connection) -> dict:
    mastery = db.execute("""SELECT capability_id, exercise_type, dimension, COUNT(*) exposures,
        SUM(result = 'success') successes, SUM(result != 'success') failures,
        MAX(CASE WHEN result = 'success' THEN difficulty END) highest_successful_difficulty,
        MAX(o.difficulty) highest_attempted_difficulty, ROUND(AVG(o.score), 3) average_score,
        ROUND(AVG(o.weight), 3) average_weight, MAX(a.attempted_at) last_seen
        FROM observations o JOIN attempts a ON a.id=o.attempt_id
        GROUP BY capability_id, exercise_type, dimension ORDER BY capability_id, exercise_type, dimension""").fetchall()
    failures = db.execute("""SELECT capability_id, failure_mode, related_capability, COUNT(*) count,
        MAX(a.attempted_at) last_seen FROM observations o JOIN attempts a ON a.id=o.attempt_id
        WHERE failure_mode IS NOT NULL GROUP BY capability_id, failure_mode, related_capability
        ORDER BY count DESC, last_seen DESC""").fetchall()
    edges = db.execute("""SELECT capability_id, edge_case, result, COUNT(*) count FROM observations
        WHERE dimension='edge' OR edge_case IS NOT NULL GROUP BY capability_id, edge_case, result""").fetchall()
    compositions = db.execute("""SELECT capability_id, related_capability, result, COUNT(*) count FROM observations
        WHERE dimension='composition' GROUP BY capability_id, related_capability, result""").fetchall()
    recent = db.execute("SELECT exercise_id, passed, score, attempted_at FROM attempts ORDER BY id DESC LIMIT 20").fetchall()
    return {"mastery": [dict(row) for row in mastery], "recurring_failures": [dict(row) for row in failures],
            "edge_evidence": [dict(row) for row in edges], "compositions": [dict(row) for row in compositions],
            "recent_activity": [dict(row) for row in recent]}
