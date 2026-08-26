"""Immutable first-party manifests and append-only cross-track provenance."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
import uuid

from fermion.source_exclusions import EXCLUDED_DIRECTORY_NAMES


SCHEMA_VERSION = "fermion-integration-provenance-v1"
DEFAULT_SOURCE_PATHS = ("fermion", "configs", "scripts", "pyproject.toml")
FIRST_PARTY_SUFFIXES = frozenset({".json", ".ps1", ".py", ".toml"})


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


@dataclass(frozen=True)
class SourceEntry:
    path: str
    sha256: str


@dataclass(frozen=True)
class FirstPartyManifest:
    schema_version: str
    source_paths: tuple[str, ...]
    entries: tuple[SourceEntry, ...]
    manifest_sha256: str

    @classmethod
    def build(cls, root: Path, source_paths: Iterable[str] = DEFAULT_SOURCE_PATHS) -> "FirstPartyManifest":
        root = root.resolve()
        paths = tuple(source_paths)
        discovered: list[SourceEntry] = []
        for declared in paths:
            candidate = (root / declared).resolve()
            if root not in candidate.parents and candidate != root:
                raise ValueError(f"source path escapes project root: {declared}")
            if not candidate.exists():
                raise FileNotFoundError(f"declared source path is missing: {declared}")
            files = [candidate] if candidate.is_file() else sorted(
                path for path in candidate.rglob("*")
                if path.is_file() and not (set(path.relative_to(root).parts) & EXCLUDED_DIRECTORY_NAMES)
                and path.suffix.lower() in FIRST_PARTY_SUFFIXES
            )
            for path in files:
                relative = path.resolve().relative_to(root).as_posix()
                discovered.append(SourceEntry(relative, sha256_file(path)))
        entries = tuple(sorted(discovered, key=lambda item: item.path))
        payload = {"schema_version": SCHEMA_VERSION, "source_paths": paths,
                   "entries": [asdict(entry) for entry in entries]}
        return cls(SCHEMA_VERSION, paths, entries, sha256_bytes(canonical_json(payload)))

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "source_paths": list(self.source_paths),
                "entries": [asdict(entry) for entry in self.entries], "manifest_sha256": self.manifest_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FirstPartyManifest":
        entries = tuple(SourceEntry(**item) for item in value["entries"])
        return cls(str(value["schema_version"]), tuple(value["source_paths"]), entries, str(value["manifest_sha256"]))

    def verify(self, root: Path) -> bool:
        rebuilt = self.build(root, self.source_paths)
        return rebuilt.manifest_sha256 == self.manifest_sha256 and rebuilt.entries == self.entries

    def write(self, path: Path) -> None:
        if path.exists():
            existing = self.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if existing.manifest_sha256 != self.manifest_sha256 or existing.entries != self.entries:
                raise FileExistsError(f"immutable manifest already exists at {path}")
            return
        _atomic_write(path, json.dumps(self.to_dict(), indent=2) + "\n")


@dataclass(frozen=True)
class ProvenanceRecord:
    record_id: str
    track: str
    state: str
    source_manifest_sha256: str
    inputs: dict[str, str]
    authority: str
    predecessor_sha256: str | None
    record_sha256: str

    @classmethod
    def create(cls, *, track: str, state: str, source_manifest_sha256: str,
               inputs: Mapping[str, str], authority: str, predecessor_sha256: str | None) -> "ProvenanceRecord":
        if not track or not state or not source_manifest_sha256 or not authority:
            raise ValueError("track, state, source manifest hash, and authority are required")
        payload = {"record_id": "prov_" + uuid.uuid4().hex, "track": track, "state": state,
                   "source_manifest_sha256": source_manifest_sha256, "inputs": dict(sorted(inputs.items())),
                   "authority": authority, "predecessor_sha256": predecessor_sha256}
        return cls(**payload, record_sha256=sha256_bytes(canonical_json(payload)))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProvenanceRecord":
        return cls(**dict(value))

    def valid_hash(self) -> bool:
        payload = self.to_dict()
        digest = payload.pop("record_sha256")
        return digest == sha256_bytes(canonical_json(payload))


class ProvenanceRegistry:
    """Append-only local registry; records never imply a scientific pass by themselves."""

    def __init__(self, path: Path):
        self.path = path

    def records(self) -> list[ProvenanceRecord]:
        if not self.path.exists():
            return []
        return [ProvenanceRecord.from_dict(json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def append(self, *, track: str, state: str, source_manifest_sha256: str,
               inputs: Mapping[str, str], authority: str) -> ProvenanceRecord:
        if not self.verify():
            raise ValueError("provenance registry integrity failure")
        records = self.records()
        record = ProvenanceRecord.create(track=track, state=state, source_manifest_sha256=source_manifest_sha256,
                                         inputs=inputs, authority=authority,
                                         predecessor_sha256=records[-1].record_sha256 if records else None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record

    def verify(self) -> bool:
        previous: str | None = None
        seen: set[str] = set()
        try:
            records = self.records()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        for record in records:
            if record.record_id in seen or not record.valid_hash() or record.predecessor_sha256 != previous:
                return False
            seen.add(record.record_id)
            previous = record.record_sha256
        return True


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
