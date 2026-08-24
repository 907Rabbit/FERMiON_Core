"""Artifact-backed scientific gate declarations; no declaration is a result by itself."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping

from .integration_registry import canonical_json, sha256_bytes, sha256_file


ALLOWED_STATES = frozenset({"blocked", "frozen_reference_verified", "gated_preexecution", "provisional", "unimplemented"})


@dataclass(frozen=True)
class ScientificGate:
    gate_id: str
    state: str
    evidence_paths: tuple[str, ...]
    evidence_sha256: dict[str, str]
    conclusion: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScientificGateRegistry:
    schema_version: str
    gates: tuple[ScientificGate, ...]
    registry_sha256: str

    @classmethod
    def build(cls, root: Path, declarations: Iterable[tuple[str, str, Iterable[str], str]]) -> "ScientificGateRegistry":
        root = root.resolve()
        gates: list[ScientificGate] = []
        for gate_id, state, paths, conclusion in declarations:
            if state not in ALLOWED_STATES:
                raise ValueError(f"unsupported or unearned scientific gate state: {state}")
            evidence_paths = tuple(paths)
            hashes: dict[str, str] = {}
            for relative in evidence_paths:
                artifact = (root / relative).resolve()
                if root not in artifact.parents or not artifact.is_file():
                    raise FileNotFoundError(f"gate evidence is unavailable: {relative}")
                hashes[relative] = sha256_file(artifact)
            if state in {"frozen_reference_verified", "gated_preexecution", "blocked"} and not hashes:
                raise ValueError(f"{state} requires durable evidence")
            gates.append(ScientificGate(gate_id, state, evidence_paths, hashes, conclusion))
        if len({gate.gate_id for gate in gates}) != len(gates):
            raise ValueError("scientific gate identifiers must be unique")
        ordered = tuple(sorted(gates, key=lambda gate: gate.gate_id))
        payload = {"schema_version": "fermion-scientific-gates-v1", "gates": [gate.to_dict() for gate in ordered]}
        return cls(payload["schema_version"], ordered, sha256_bytes(canonical_json(payload)))

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "gates": [gate.to_dict() for gate in self.gates],
                "registry_sha256": self.registry_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ScientificGateRegistry":
        gates = tuple(ScientificGate(
            gate_id=str(item["gate_id"]), state=str(item["state"]),
            evidence_paths=tuple(item["evidence_paths"]), evidence_sha256=dict(item["evidence_sha256"]),
            conclusion=str(item["conclusion"]),
        ) for item in value["gates"])
        return cls(str(value["schema_version"]), gates, str(value["registry_sha256"]))

    def verify(self, root: Path) -> bool:
        root = root.resolve()
        payload = {"schema_version": self.schema_version, "gates": [gate.to_dict() for gate in self.gates]}
        if self.registry_sha256 != sha256_bytes(canonical_json(payload)):
            return False
        for gate in self.gates:
            for relative, digest in gate.evidence_sha256.items():
                artifact = (root / relative).resolve()
                if root not in artifact.parents or not artifact.is_file() or sha256_file(artifact) != digest:
                    return False
        return True

    def write(self, path: Path) -> None:
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if canonical_json(existing) != canonical_json(self.to_dict()):
                raise FileExistsError(f"immutable scientific gate registry already exists at {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(path)


def bootstrap_declarations() -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    return (
        ("AI-G2S-P1.0", "blocked", ("artifacts/ai_g2s_r1/protocol_coverage.json",),
         "Protocol coverage artifact records unresolved construction blockers; no execution result is claimed."),
        ("AI-G2S-P1.1", "gated_preexecution", ("configs/ai_g2s_p1_1.json", "artifacts/ai_g2s_r1_1_repaired/launch_readiness_audit.json"),
         "Pre-execution protocol and readiness evidence exist; full paired execution and final predictions remain unperformed."),
        ("CP10", "unimplemented", (), "No implemented first-party CP10 gate was located in the Phase 1 audit."),
        ("CP11", "unimplemented", (), "No implemented first-party CP11 gate was located in the Phase 1 audit."),
        ("GSE", "provisional", (), "GSE code hooks exist, but no artifact-backed scientific utility conclusion is recorded."),
        ("HR-193", "frozen_reference_verified", ("fermion/hr/reference_193.py",),
         "Reference source bytes match the recorded AI-G2S P1.1 manifest value; this is not a performance claim."),
        ("MFE", "unimplemented", (), "No implemented first-party MFE component was located in the Phase 1 audit."),
        ("PhiLang", "unimplemented", (), "No implemented first-party PhiLang component was located in the Phase 1 audit."),
        ("Psilang", "unimplemented", (), "No implemented first-party Psilang component was located in the Phase 1 audit."),
    )
