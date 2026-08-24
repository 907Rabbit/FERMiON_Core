"""Verified composition root for the local unified FERMiON runtime."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fermion.control_plane import default_control_plane

from .integration_registry import FirstPartyManifest, ProvenanceRegistry
from .integration_runtime import FermionRuntime
from .scientific_gates import ScientificGateRegistry


@dataclass(frozen=True)
class BootstrappedRuntime:
    runtime: FermionRuntime
    manifest: FirstPartyManifest
    scientific_gates: ScientificGateRegistry


@dataclass(frozen=True)
class GitBaseline:
    repository_present: bool
    committed: bool
    head: str | None
    clean: bool | None

    @property
    def status(self) -> str:
        if not self.repository_present:
            return "NO_GIT_BASELINE"
        if not self.committed:
            return "UNCOMMITTED_BASELINE"
        return "COMMITTED_CLEAN" if self.clean else "COMMITTED_DIRTY"


def inspect_git_baseline(root: Path) -> GitBaseline:
    """Read Git state only; a source hash manifest does not create a Git baseline."""
    root = root.resolve()
    if not (root / ".git").exists():
        return GitBaseline(False, False, None, None)
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(("git", "-C", str(root), *arguments), text=True, capture_output=True, check=False)
    head = run("rev-parse", "--verify", "HEAD")
    if head.returncode:
        return GitBaseline(True, False, None, None)
    status = run("status", "--porcelain")
    if status.returncode:
        return GitBaseline(True, True, head.stdout.strip(), None)
    return GitBaseline(True, True, head.stdout.strip(), not bool(status.stdout.strip()))


def verify_integration(*, root: Path, manifest_path: Path, gate_registry_path: Path) -> tuple[FirstPartyManifest, ScientificGateRegistry, ProvenanceRegistry]:
    """Verify integration artifacts without constructing a runtime or taking an action."""
    root = root.resolve()
    for path in (manifest_path, gate_registry_path):
        resolved = path.resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise FileNotFoundError(f"required bootstrap artifact is unavailable: {path}")
    manifest = FirstPartyManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    if not manifest.verify(root):
        raise ValueError("first-party source manifest verification failed")
    gates = ScientificGateRegistry.from_dict(json.loads(gate_registry_path.read_text(encoding="utf-8")))
    if not gates.verify(root):
        raise ValueError("scientific gate registry verification failed")
    provenance = ProvenanceRegistry(root / "artifacts" / "integration_provenance.jsonl")
    if not provenance.verify():
        raise ValueError("integration provenance registry verification failed")
    return manifest, gates, provenance


def load_verified_runtime(*, root: Path, manifest_path: Path, gate_registry_path: Path,
                          control_runtime_root: Path) -> BootstrappedRuntime:
    """Load only artifact-backed configuration; never execute a user plan here."""
    manifest, gates, provenance = verify_integration(root=root, manifest_path=manifest_path,
                                                      gate_registry_path=gate_registry_path)
    return BootstrappedRuntime(
        runtime=FermionRuntime(control_plane=default_control_plane(control_runtime_root), registry=provenance,
                               source_root=root, source_manifest=manifest),
        manifest=manifest, scientific_gates=gates,
    )
