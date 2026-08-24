from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.release_governance import ReleaseGovernor
from fermion.cognitive.release_candidates import ReleaseCandidateService, ReleaseCandidateEvidence

def service(tmp_path):
    (tmp_path/"tests").mkdir(exist_ok=True);(tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n")
    return ReleaseCandidateService(tmp_path,ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path)))
def test_candidate_hash_tamper_is_rejected(tmp_path):
    candidate=service(tmp_path).create(); candidate.payload["verdict"]="tampered"
    assert service(tmp_path).verify(candidate)["failure_reason"] == "RELEASE_HASH_MISMATCH"
def test_untrusted_and_missing_signature_are_distinct(tmp_path):
    candidate=service(tmp_path).create()
    assert service(tmp_path).verify(candidate)["failure_reason"] == "RELEASE_SIGNATURE_MISSING"
    assert service(tmp_path).verify(candidate,{"key_id":"x","signature":""},{})["failure_reason"] == "RELEASE_KEY_UNTRUSTED"
