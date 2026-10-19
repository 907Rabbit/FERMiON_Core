import hashlib
import json

import pytest

from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.release_governance import ReleaseGovernor
from fermion.cognitive.release_candidates import ReleaseCandidateService, canonical
from fermion.cognitive.reproducibility import BundleService


def bundle(tmp_path):
    (tmp_path/"tests").mkdir(exist_ok=True)
    (tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n",encoding="utf-8")
    return BundleService(tmp_path,ReleaseCandidateService(tmp_path,ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path))))


def rehash_bundle(path, data):
    data.pop("bundle_sha256",None)
    data["bundle_sha256"] = hashlib.sha256(canonical(data)).hexdigest()
    path.write_text(json.dumps(data),encoding="utf-8")


def test_bundle_integrity_does_not_claim_release_or_reproduction_authority(tmp_path):
    service = bundle(tmp_path)
    path = service.create()
    result = service.verify(path)
    assert result["verdict"] == "BUNDLE_INTEGRITY_VERIFIED_UNSIGNED"
    assert result["signature_verified"] is False
    assert result["release_authority_verified"] is False
    reproduced = service.reproduce_diprotic(path)
    assert reproduced["verdict"] == "REPRODUCTION_UNVERIFIED"
    assert reproduced["semantic_hash_match"] is None
    assert reproduced["oracle_verdicts_match"] is None
    assert "local_calculation_id" not in reproduced
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["artifacts"]["environment_fingerprint"] is None
    assert data["artifacts"]["benchmark_manifest"] is None


def test_bundle_tamper_is_detected(tmp_path):
    service = bundle(tmp_path)
    path = service.create()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["trust"]["reason"] = "tampered"
    path.write_text(json.dumps(data),encoding="utf-8")
    assert service.verify(path)["verdict"] == "BUNDLE_HASH_MISMATCH"


def test_self_declared_signature_cannot_be_verified_by_recomputing_checksum(tmp_path):
    service = bundle(tmp_path)
    path = service.create()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["trust"]["signed"] = True
    rehash_bundle(path,data)
    assert service.verify(path)["verdict"] == "BUNDLE_SIGNATURE_UNVERIFIED"
    assert service.reproduce_diprotic(path)["verdict"] == "EVIDENCE_INCOMPLETE"


def test_outer_checksum_does_not_substitute_for_nested_artifact_binding(tmp_path):
    service = bundle(tmp_path)
    path = service.create()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["release_candidate"]["payload"]["verdict"] = "RELEASE_READY"
    rehash_bundle(path,data)
    assert service.verify(path)["verdict"] == "BUNDLE_ARTIFACT_HASH_MISMATCH"
    data["artifacts"]["release_candidate"] = hashlib.sha256(canonical(data["release_candidate"])).hexdigest()
    rehash_bundle(path,data)
    assert service.verify(path)["verdict"] == "BUNDLE_RELEASE_HASH_MISMATCH"


def test_bundle_with_arbitrary_receipt_is_not_reproduced_as_a_fixed_fixture(tmp_path):
    service = bundle(tmp_path)
    path = service.create()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["normalized_evidence"]["calculation_receipts"] = [{"problem_type":"unrelated","pH":99}]
    rehash_bundle(path,data)
    assert service.reproduce_diprotic(path)["verdict"] == "REPRODUCTION_UNVERIFIED"


@pytest.mark.parametrize("text", ['{"schema_version":1,"schema_version":1}',
                                 '{"value":NaN}', '{"value":1e999}', '[]', '{'])
def test_invalid_or_ambiguous_bundle_is_rejected(tmp_path,text):
    path = tmp_path/"invalid.json"
    path.write_text(text,encoding="utf-8")
    assert bundle(tmp_path).verify(path)["verdict"] == "BUNDLE_INVALID"


@pytest.mark.parametrize("claimed_signed", [1,"false",None])
def test_signature_claim_requires_an_exact_boolean(tmp_path,claimed_signed):
    service = bundle(tmp_path)
    path = service.create()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["trust"]["signed"] = claimed_signed
    rehash_bundle(path,data)
    assert service.verify(path)["verdict"] == "BUNDLE_INVALID"
