import json

import pytest

from fermion.cognitive.scientific_gates import ScientificGateRegistry


def test_gate_registry_hashes_evidence_and_detects_tampering(tmp_path):
    (tmp_path / "artifacts").mkdir()
    evidence = tmp_path / "artifacts" / "gate.json"
    evidence.write_text('{"state":"gated"}\n', encoding="utf-8")
    registry = ScientificGateRegistry.build(tmp_path, (
        ("gate", "gated_preexecution", ("artifacts/gate.json",), "No result claimed."),
        ("future", "unimplemented", (), "Not implemented."),
    ))
    assert registry.verify(tmp_path)
    destination = tmp_path / "artifacts" / "scientific-gates.json"
    registry.write(destination)
    registry.write(destination)
    evidence.write_text('{"state":"changed"}\n', encoding="utf-8")
    assert not registry.verify(tmp_path)
    with pytest.raises(FileExistsError):
        ScientificGateRegistry.build(tmp_path, (("gate", "gated_preexecution", ("artifacts/gate.json",), "Changed."),)).write(destination)


def test_gate_registry_rejects_unearned_state_and_missing_required_evidence(tmp_path):
    with pytest.raises(ValueError):
        ScientificGateRegistry.build(tmp_path, (("gate", "passed", (), "Unsupported."),))
    with pytest.raises(ValueError):
        ScientificGateRegistry.build(tmp_path, (("gate", "blocked", (), "Evidence missing."),))


def test_gate_registry_serialization_is_self_hashing(tmp_path):
    registry = ScientificGateRegistry.build(tmp_path, (("future", "provisional", (), "No result."),))
    payload = registry.to_dict()
    assert payload["registry_sha256"] == registry.registry_sha256
    assert json.loads(json.dumps(payload))["gates"][0]["state"] == "provisional"
