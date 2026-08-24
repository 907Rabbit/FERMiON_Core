import json

import pytest

from fermion.cognitive.integration_registry import FirstPartyManifest, ProvenanceRegistry
from fermion.cognitive.runtime_bootstrap import inspect_git_baseline, load_verified_runtime, verify_integration
from fermion.cognitive.scientific_gates import ScientificGateRegistry


def setup_project(tmp_path):
    root = tmp_path / "project"
    (root / "fermion").mkdir(parents=True); (root / "fermion" / "core.py").write_text("VALUE = 1\n")
    (root / "configs").mkdir(); (root / "configs" / "gate.json").write_text("{}\n")
    (root / "scripts").mkdir(); (root / "scripts" / "launch.ps1").write_text("safe\n")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    artifacts = root / "artifacts"; artifacts.mkdir()
    manifest = FirstPartyManifest.build(root); manifest_path = artifacts / "manifest.json"; manifest.write(manifest_path)
    evidence = artifacts / "gate-evidence.json"; evidence.write_text("{}\n")
    gates = ScientificGateRegistry.build(root, (("gate", "gated_preexecution", ("artifacts/gate-evidence.json",), "Not run."),))
    gates_path = artifacts / "gates.json"; gates.write(gates_path)
    provenance = ProvenanceRegistry(artifacts / "integration_provenance.jsonl")
    provenance.append(track="test", state="bootstrap_recorded", source_manifest_sha256=manifest.manifest_sha256,
                      inputs={}, authority="test")
    return root, manifest_path, gates_path


def test_bootstrap_requires_verified_artifacts_and_creates_nonexecuting_runtime(tmp_path):
    root, manifest_path, gates_path = setup_project(tmp_path)
    bootstrapped = load_verified_runtime(root=root, manifest_path=manifest_path, gate_registry_path=gates_path,
                                         control_runtime_root=tmp_path / "control")
    assert bootstrapped.manifest.verify(root)
    assert bootstrapped.scientific_gates.verify(root)
    assert bootstrapped.runtime.registry.verify()


def test_read_only_verification_does_not_construct_a_control_plane_runtime(tmp_path):
    root, manifest_path, gates_path = setup_project(tmp_path)
    manifest, gates, provenance = verify_integration(root=root, manifest_path=manifest_path, gate_registry_path=gates_path)
    assert manifest.verify(root) and gates.verify(root) and provenance.verify()
    assert not (tmp_path / "control").exists()


def test_bootstrap_rejects_source_or_gate_evidence_drift(tmp_path):
    root, manifest_path, gates_path = setup_project(tmp_path)
    (root / "fermion" / "core.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="manifest"):
        load_verified_runtime(root=root, manifest_path=manifest_path, gate_registry_path=gates_path,
                              control_runtime_root=tmp_path / "control")
    # Restore source, then tamper the gate evidence referenced by the registry.
    (root / "fermion" / "core.py").write_text("VALUE = 1\n")
    (root / "artifacts" / "gate-evidence.json").write_text('{"changed":true}\n')
    with pytest.raises(ValueError, match="gate registry"):
        load_verified_runtime(root=root, manifest_path=manifest_path, gate_registry_path=gates_path,
                              control_runtime_root=tmp_path / "control")


def test_bootstrap_rejects_tampered_provenance_chain(tmp_path):
    root, manifest_path, gates_path = setup_project(tmp_path)
    provenance_path = root / "artifacts" / "integration_provenance.jsonl"
    provenance_path.write_text(json.dumps({"record_id": "fake"}) + "\n")
    with pytest.raises(ValueError, match="provenance"):
        load_verified_runtime(root=root, manifest_path=manifest_path, gate_registry_path=gates_path,
                              control_runtime_root=tmp_path / "control")


def test_git_baseline_inspection_never_conflates_a_nonrepository_with_a_frozen_baseline(tmp_path):
    baseline = inspect_git_baseline(tmp_path)
    assert baseline.status == "NO_GIT_BASELINE"
    assert not baseline.committed and baseline.head is None and baseline.clean is None
