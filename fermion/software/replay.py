"""Frozen execution traces for offline training and audit."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReplayRecord:
    goal: str
    candidates: list[dict[str, Any]]
    selected_id: str
    observation_before: dict[str, Any]
    observation_after: dict[str, Any]
    execution: dict[str, Any]
    decision: dict[str, Any]
    timestamp: float
    record_id: int | None = None


class ReplayDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS replay (id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, payload TEXT NOT NULL)"
        )
        self.connection.commit()

    def append(self, record: ReplayRecord) -> int:
        payload = asdict(record); payload.pop("record_id", None)
        cursor = self.connection.execute("INSERT INTO replay VALUES (NULL,?,?)",
                                         (record.timestamp, json.dumps(payload, sort_keys=True)))
        self.connection.commit()
        return int(cursor.lastrowid)

    def records(self) -> list[ReplayRecord]:
        result = []
        for record_id, _, payload in self.connection.execute("SELECT id,timestamp,payload FROM replay ORDER BY id"):
            value = json.loads(payload)
            result.append(ReplayRecord(**value, record_id=record_id))
        return result

    def close(self) -> None:
        self.connection.close()

    def __len__(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM replay").fetchone()[0])

