from dataclasses import replace

from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.release_governance import ReleaseGovernor
from fermion.cognitive.release_candidates import ReleaseCandidateService, ReleaseCandidateEvidence

def service(tmp_path, *, assume_test_readiness=False):
    (tmp_path/"tests").mkdir(exist_ok=True);(tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n")
    governor = ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path))
    if assume_test_readiness:
        # Signature-boundary fixture only; actual readiness remains fail-closed.
        ready = replace(governor.evaluate(), verdict="RELEASE_READY", blockers=())
        class ReadyFixture:
            def evaluate(self): return ready
        governor = ReadyFixture()
    return ReleaseCandidateService(tmp_path,governor)
def test_candidate_hash_tamper_is_rejected(tmp_path):
    candidate=service(tmp_path).create(); candidate.payload["verdict"]="tampered"
    assert service(tmp_path).verify(candidate)["failure_reason"] == "RELEASE_HASH_MISMATCH"
def test_untrusted_and_missing_signature_are_distinct(tmp_path):
    candidate=service(tmp_path,assume_test_readiness=True).create()
    assert service(tmp_path).verify(candidate)["failure_reason"] == "RELEASE_SIGNATURE_MISSING"
    assert service(tmp_path).verify(candidate,{"key_id":"x","signature":""},{})["failure_reason"] == "RELEASE_KEY_UNTRUSTED"

def test_unverified_release_cannot_enter_signature_authorization(tmp_path):
    candidate=service(tmp_path).create()
    assert candidate.verdict == "RELEASE_BLOCKED"
    assert service(tmp_path).verify(candidate)["valid"] is False
