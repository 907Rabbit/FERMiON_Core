"""Verified composition root for the local unified FERMiON runtime."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fermion.control_plane import ApplicationControlPlane, default_control_plane, default_runtime_root

from .integration_registry import FirstPartyManifest, ProvenanceRegistry
from .integration_runtime import FermionRuntime
from .scientific_gates import ScientificGateRegistry

DEFAULT_MANIFEST = "artifacts/first_party_manifest.json"
DEFAULT_GATES = "artifacts/scientific_gate_registry.json"
DEFAULTS_POINTER = "artifacts/integration_defaults.json"


def integration_artifact_paths(root: Path) -> tuple[Path, Path]:
    """Resolve the current immutable manifest/gate files; a pointer may retarget them."""
    root = root.resolve()
    pointer = root / DEFAULTS_POINTER
    if pointer.is_file():
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        return root / str(payload["manifest"]), root / str(payload["gates"])
    return root / DEFAULT_MANIFEST, root / DEFAULT_GATES


def shared_control_plane(root: Path, *, control_runtime_root: Path | None = None) -> ApplicationControlPlane:
    """One control-plane factory for chat, dashboard, and verified composition."""
    if control_runtime_root is not None:
        return default_control_plane(control_runtime_root)
    artifacts = root / "artifacts"
    if (artifacts / "first_party_manifest.json").is_file() or (artifacts / "integration_defaults.json").is_file():
        return default_control_plane(default_runtime_root())
    return default_control_plane(root / ".fermion_control")


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
    tracked_clean: bool | None
    untracked_count: int

    @property
    def status(self) -> str:
        if not self.repository_present:
            return "NO_GIT_BASELINE"
        if not self.committed:
            return "UNCOMMITTED_BASELINE"
        if not self.tracked_clean:
            return "COMMITTED_TRACKED_DRIFT"
        return "COMMITTED_CLEAN" if not self.untracked_count else "COMMITTED_TRACKED_CLEAN_UNTRACKED_PRESENT"


def inspect_git_baseline(root: Path) -> GitBaseline:
    """Read Git state only; a source hash manifest does not create a Git baseline."""
    root = root.resolve()
    if not (root / ".git").exists():
        return GitBaseline(False, False, None, None, 0)
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(("git", "-C", str(root), *arguments), text=True, capture_output=True, check=False)
    head = run("rev-parse", "--verify", "HEAD")
    if head.returncode:
        return GitBaseline(True, False, None, None, 0)
    status = run("status", "--porcelain")
    if status.returncode:
        return GitBaseline(True, True, head.stdout.strip(), None, 0)
    lines = [line for line in status.stdout.splitlines() if line]
    return GitBaseline(True, True, head.stdout.strip(),
                       not any(not line.startswith("??") for line in lines),
                       sum(line.startswith("??") for line in lines))


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
        runtime=FermionRuntime(control_plane=shared_control_plane(root, control_runtime_root=control_runtime_root),
                               registry=provenance, source_root=root, source_manifest=manifest),
        manifest=manifest, scientific_gates=gates,
    )


def try_load_verified_runtime(root: Path, *, control_runtime_root: Path | None = None) -> BootstrappedRuntime | None:
    """Return a verified composition root, or None when artifacts are absent or fail closed."""
    manifest_path, gates_path = integration_artifact_paths(root)
    if not manifest_path.is_file() or not gates_path.is_file():
        return None
    try:
        return load_verified_runtime(root=root, manifest_path=manifest_path, gate_registry_path=gates_path,
                                     control_runtime_root=control_runtime_root or default_runtime_root())
    except (OSError, ValueError, FileNotFoundError):
        return None
