import json
from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.release_governance import ReleaseGovernor
from fermion.cognitive.release_candidates import ReleaseCandidateService
from fermion.cognitive.reproducibility import BundleService
def bundle(tmp_path):
    (tmp_path/"tests").mkdir(exist_ok=True);(tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n")
    return BundleService(tmp_path,ReleaseCandidateService(tmp_path,ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path))))
def test_bundle_verifies_unsigned_and_reproduces(tmp_path):
    path=bundle(tmp_path).create(); assert bundle(tmp_path).verify(path)["verdict"]=="VERIFIED_UNSIGNED";assert bundle(tmp_path).reproduce_diprotic(path)["verdict"]=="REPRODUCED"
def test_bundle_tamper_is_detected(tmp_path):
    path=bundle(tmp_path).create();data=json.loads(path.read_text());data["trust"]["reason"]="tampered";path.write_text(json.dumps(data));assert bundle(tmp_path).verify(path)["verdict"]=="BUNDLE_HASH_MISMATCH"
