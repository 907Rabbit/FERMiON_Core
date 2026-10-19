"""Persistent typed text memory with evidence-aware vector retrieval."""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .embeddings import EmbeddingClient, cosine, hashed_embed


def embed(text: str, dimensions: int = 96) -> list[float]:
    """Hashed fallback used by the quarantined GRU path; not a semantic index."""
    return hashed_embed(text, dimensions)


@dataclass(frozen=True)
class MemoryItem:
    kind: str
    content: str
    importance: float = 0.7
    metadata: dict[str, object] | None = None
    timestamp: float = 0.0


class CognitiveMemory:
    KINDS = ("working", "episodic", "semantic", "procedural", "goal", "self")
    def __init__(self, path: str | Path, embedder: EmbeddingClient | None = None):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or EmbeddingClient()
        self.db = sqlite3.connect(self.path)
        self.db.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, kind TEXT, content TEXT, vector TEXT, importance REAL, metadata TEXT, timestamp REAL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS semantic_records (canonical_key TEXT PRIMARY KEY, memory_id INTEGER NOT NULL, stored_value TEXT NOT NULL, content_hash TEXT NOT NULL, committed_at TEXT NOT NULL, receipt_id TEXT NOT NULL)")
        self.db.commit()
        self.working: list[str] = []
        self.last_retrieval_backend = self.embedder.backend

    def remember(self, item: MemoryItem) -> int:
        if item.kind not in self.KINDS: raise ValueError(f"unknown memory kind: {item.kind}")
        timestamp = item.timestamp or time.time()
        if item.kind == "working": self.working = (self.working + [item.content])[-12:]
        result = self.embedder.embed_result(item.content)
        metadata = dict(item.metadata or {})
        metadata["embedder"] = result.backend
        metadata["embedder_model"] = result.model
        cursor = self.db.execute("INSERT INTO memories(kind,content,vector,importance,metadata,timestamp) VALUES (?,?,?,?,?,?)", (item.kind, item.content, json.dumps(result.vector), item.importance, json.dumps(metadata), timestamp))
        self.db.commit(); return int(cursor.lastrowid)

    def retrieve(self, query: str, limit: int = 5, *, kinds: tuple[str, ...] | None = None,
                 minimum_score: float = 0.35) -> list[MemoryItem]:
        result = self.embedder.embed_result(query)
        self.last_retrieval_backend = result.backend
        vector, now, scored = result.vector, time.time(), []
        for kind, content, saved, importance, metadata, timestamp in self.db.execute("SELECT kind,content,vector,importance,metadata,timestamp FROM memories"):
            if kinds is not None and kind not in kinds: continue
            other = json.loads(saved)
            if not isinstance(other, list) or len(other) != len(vector):
                continue
            similarity = cosine(vector, [float(value) for value in other])
            score = similarity + .15 * importance - min((now - timestamp) / 315360000, .08)
            if score >= minimum_score: scored.append((score, MemoryItem(kind, content, importance, json.loads(metadata), timestamp)))
        return [item for _, item in sorted(scored, reverse=True, key=lambda pair: pair[0])[:limit]]

    def close(self) -> None: self.db.close()

    def record_semantic_receipt(self, *, canonical_key: str, memory_id: int, stored_value: str,
                                content_hash: str, committed_at: str, receipt_id: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO semantic_records VALUES (?,?,?,?,?,?)", (canonical_key, memory_id, stored_value, content_hash, committed_at, receipt_id))
        self.db.commit()

    def verify_semantic(self, canonical_key: str) -> dict[str, object] | None:
        row = self.db.execute("SELECT canonical_key,memory_id,stored_value,content_hash,committed_at,receipt_id FROM semantic_records WHERE canonical_key = ?", (canonical_key,)).fetchone()
        if row is None: return None
        return {"canonical_key": row[0], "memory_id": f"mem_{row[1]}", "stored_value": row[2], "content_hash": row[3], "committed_at": row[4], "memory_receipt_id": row[5], "database_path": str(self.path.resolve())}

    def semantic_receipts(self) -> list[dict[str, object]]:
        rows = self.db.execute("SELECT canonical_key,memory_id,stored_value,content_hash,committed_at,receipt_id FROM semantic_records").fetchall()
        return [{"canonical_key": row[0], "memory_id": f"mem_{row[1]}", "stored_value": row[2], "content_hash": row[3], "committed_at": row[4], "memory_receipt_id": row[5], "database_path": str(self.path.resolve())} for row in rows]
