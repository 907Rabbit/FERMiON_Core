import json

import pytest

from fermion.cognitive.integration_registry import FirstPartyManifest, ProvenanceRegistry


def project(tmp_path):
    (tmp_path / "fermion").mkdir()
    (tmp_path / "fermion" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "gate.json").write_text('{"state":"gated"}\n', encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.ps1").write_text("Write-Output safe\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return tmp_path


def test_first_party_manifest_is_deterministic_and_detects_source_change(tmp_path):
    root = project(tmp_path)
    (root / "fermion" / "__pycache__").mkdir()
    (root / "fermion" / "__pycache__" / "core.pyc").write_bytes(b"runtime")
    (root / "fermion" / "spiderfoot").mkdir()
    (root / "fermion" / "spiderfoot" / "third_party.py").write_text("unsafe = True\n", encoding="utf-8")
    manifest = FirstPartyManifest.build(root)
    assert {entry.path for entry in manifest.entries} == {
        "configs/gate.json", "fermion/core.py", "pyproject.toml", "scripts/run.ps1",
    }
    assert manifest.verify(root)
    destination = root / "artifacts" / "first-party-manifest.json"
    manifest.write(destination)
    manifest.write(destination)
    assert FirstPartyManifest.from_dict(json.loads(destination.read_text())).verify(root)
    (root / "fermion" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert not manifest.verify(root)
    with pytest.raises(FileExistsError):
        FirstPartyManifest.build(root).write(destination)


def test_manifest_rejects_missing_or_escaping_declared_source_path(tmp_path):
    root = project(tmp_path)
    with pytest.raises(FileNotFoundError):
        FirstPartyManifest.build(root, ("missing",))
    with pytest.raises(ValueError):
        FirstPartyManifest.build(root, ("..",))


def test_provenance_registry_is_append_only_hash_chained_and_detects_tampering(tmp_path):
    registry = ProvenanceRegistry(tmp_path / "artifacts" / "provenance.jsonl")
    first = registry.append(track="HR-193", state="frozen", source_manifest_sha256="A" * 64,
                            inputs={"reference": "B" * 64}, authority="inspection")
    second = registry.append(track="AI-G2S-P1.1", state="gated", source_manifest_sha256="A" * 64,
                             inputs={"protocol": "C" * 64}, authority="explicit-user-launch-required")
    assert second.predecessor_sha256 == first.record_sha256
    assert registry.verify()
    text = registry.path.read_text(encoding="utf-8")
    registry.path.write_text(text.replace('"state":"gated"', '"state":"passed"'), encoding="utf-8")
    assert not registry.verify()
    with pytest.raises(ValueError):
        registry.append(track="AI-G2S-P1.1", state="gated", source_manifest_sha256="A" * 64,
                        inputs={}, authority="inspection")
