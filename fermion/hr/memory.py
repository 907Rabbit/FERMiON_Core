"""Persistent episodic memory with reliability-aware retrieval."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MemoryRecord:
    key: tuple[float, ...]
    value: tuple[float, ...]
    observation: dict[str, Any]
    action: dict[str, Any]
    result: dict[str, Any]
    recovery: dict[str, Any]
    reliability: float
    confidence: float
    timestamp: float
    record_id: int | None = None


@dataclass(frozen=True)
class RetrievedMemory:
    record: MemoryRecord
    score: float


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


class EpisodicMemory:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY, key_json TEXT NOT NULL, value_json TEXT NOT NULL,
            observation_json TEXT NOT NULL, action_json TEXT NOT NULL,
            result_json TEXT NOT NULL, recovery_json TEXT NOT NULL,
            reliability REAL NOT NULL, confidence REAL NOT NULL, timestamp REAL NOT NULL)"""
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def write(self, record: MemoryRecord, *, novelty: float = 1.0,
              energy_change: float = 0.0, information_gain: float = 1.0,
              failure_significance: float = 0.0, threshold: float = 0.5) -> int | None:
        signal = novelty + abs(energy_change) + information_gain + failure_significance - 1.5
        probability = 1.0 / (1.0 + math.exp(-signal))
        if probability < threshold:
            return None
        cursor = self.connection.execute(
            "INSERT INTO episodes VALUES (NULL,?,?,?,?,?,?,?,?,?)",
            (json.dumps(record.key), json.dumps(record.value), json.dumps(record.observation),
             json.dumps(record.action), json.dumps(record.result), json.dumps(record.recovery),
             record.reliability, record.confidence, record.timestamp),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def retrieve(self, query: tuple[float, ...], limit: int = 5, now: float | None = None,
                 similarity_weight: float = 1.0, reliability_weight: float = 0.5,
                 confidence_weight: float = 0.25, age_weight: float = 0.01) -> list[RetrievedMemory]:
        now = time.time() if now is None else now
        rows = self.connection.execute("SELECT * FROM episodes").fetchall()
        scored: list[RetrievedMemory] = []
        for row in rows:
            record = MemoryRecord(tuple(json.loads(row[1])), tuple(json.loads(row[2])),
                                  json.loads(row[3]), json.loads(row[4]), json.loads(row[5]),
                                  json.loads(row[6]), row[7], row[8], row[9], row[0])
            age_days = max(0.0, now - record.timestamp) / 86400.0
            score = (similarity_weight * cosine(query, record.key)
                     + reliability_weight * record.reliability
                     + confidence_weight * record.confidence - age_weight * age_days)
            scored.append(RetrievedMemory(record, score))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def __len__(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM episodes").fetchone()[0])

