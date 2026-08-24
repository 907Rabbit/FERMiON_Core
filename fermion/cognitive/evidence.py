"""Typed evidence created only by FERMiON stores and executors, never by an LLM."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

def utc_now() -> str: return datetime.now(timezone.utc).isoformat()
def canonical_json(value: object) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

@dataclass(frozen=True)
class ExecutionEvidence:
    evidence_id: str; tool_name: str; command: tuple[str, ...]; cwd: str; exit_code: int | None
    stdout: str; stderr: str; started_at: str; finished_at: str; artifact_hashes: dict[str, str]
    @classmethod
    def create(cls, command: list[str], cwd: Path, exit_code: int | None, stdout: str, stderr: str,
               started_at: str, artifacts: list[Path]) -> "ExecutionEvidence":
        hashes = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts if path.is_file()}
        return cls("exec_" + uuid.uuid4().hex, "python_executor", tuple(command), str(cwd.resolve()), exit_code, stdout, stderr, started_at, utc_now(), hashes)
    def to_dict(self) -> dict[str, object]: return {"executed": self.exit_code == 0, "evidence_id": self.evidence_id, "tool_name": self.tool_name, "absolute_file_path": next(iter(self.artifact_hashes), ""), "file_sha256": next(iter(self.artifact_hashes.values()), ""), "exact_command": list(self.command), "cwd": self.cwd, "exit_code": self.exit_code, "stdout": self.stdout, "stderr": self.stderr, "started_at": self.started_at, "finished_at": self.finished_at, "artifact_hashes": self.artifact_hashes}

@dataclass(frozen=True)
class MemoryReceipt:
    receipt_id: str; memory_id: int; memory_type: str; canonical_key: str; value: str
    content_hash: str; database_path: str; committed_at: str
    @classmethod
    def create(cls, memory_id: int, memory_type: str, key: str, value: str, database_path: Path) -> "MemoryReceipt":
        committed = utc_now(); digest = hashlib.sha256(f"{key}={value}".encode()).hexdigest()
        return cls("memr_" + uuid.uuid4().hex, memory_id, memory_type, key, value, digest, str(database_path.resolve()), committed)
    def to_dict(self) -> dict[str, object]: return {"committed": True, "memory_receipt_id": self.receipt_id, "memory_id": f"mem_{self.memory_id}", "memory_type": self.memory_type, "canonical_key": self.canonical_key, "stored_value": self.value, "content_hash": self.content_hash, "database_path": self.database_path, "committed_at": self.committed_at}

@dataclass(frozen=True)
class CapabilityChangeEvidence:
    """Governance receipt for externally authorized changes; registry inspection cannot create it."""
    change_id: str; target_capability: str; parent_baseline_hash: str; files_changed: tuple[str,...]
    patch_hash: str; verification: dict[str, object]; before_state: dict[str,object]; after_state: dict[str,object]; decision: str; reason: str|None=None
    def to_dict(self) -> dict[str,object]: return asdict(self)

@dataclass(frozen=True)
class WebEvidence:
    evidence_id:str; url:str; retrieved_at:str; status_code:int|None; content_sha256:str; content_excerpt:str; source_status:str
    def to_dict(self)->dict[str,object]:return asdict(self)


class EvidenceLedger:
    """Append-only receipt ledger; IDs are resolved from this ledger, never regenerated."""
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, receipt: object) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(canonical_json({"kind": kind, "receipt": receipt.to_dict()}) + "\n")

    def last(self) -> dict[str, object] | None:
        if not self.path.is_file(): return None
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return json.loads(lines[-1]) if lines else None

    def records(self) -> list[dict[str, object]]:
        """Return persisted receipts exactly as stored, in append order."""
        if not self.path.is_file(): return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def execution(self, evidence_id: str) -> dict[str, object] | None:
        return self._find("execution", "evidence_id", evidence_id)

    def memory(self, key: str) -> dict[str, object] | None:
        return self._find("memory", "canonical_key", key)

    def calculation(self, calculation_id: str) -> dict[str, object] | None:
        return self._find("calculation", "calculation_id", calculation_id)

    def last_calculation(self) -> dict[str, object] | None:
        if not self.path.is_file(): return None
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            item = json.loads(line)
            if item.get("kind") == "calculation": return item
        return None
    def calculation_type(self, problem_type: str) -> dict[str, object] | None:
        if not self.path.is_file(): return None
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            item=json.loads(line)
            if item.get("kind")=="calculation" and item.get("receipt",{}).get("problem_type")==problem_type:return item
        return None

    def _find(self, kind: str, field: str, expected: str) -> dict[str, object] | None:
        if not self.path.is_file(): return None
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            item = json.loads(line)
            if item.get("kind") == kind and item.get("receipt", {}).get(field) == expected: return item
        return None
