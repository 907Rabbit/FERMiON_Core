"""Bundle integrity inspection, separate from signature and reproduction authority."""
from __future__ import annotations
import hashlib,json,uuid
from pathlib import Path
from .release_candidates import ReleaseCandidateService,canonical

class BundleService:
    def __init__(self,root:Path,candidates:ReleaseCandidateService):self.root=root;self.candidates=candidates
    def create(self)->Path:
        candidate=self.candidates.create().to_dict(); receipts=[]; ledger=self.root/"logs"/"receipts.jsonl"
        if ledger.exists(): receipts=[json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if 'calculation' in x][-10:]
        artifacts={"release_candidate":hashlib.sha256(canonical(candidate)).hexdigest(),
                   "environment_fingerprint":None,"benchmark_manifest":None,
                   "configuration_manifest":hashlib.sha256((self.root/"pyproject.toml").read_bytes()).hexdigest() if (self.root/"pyproject.toml").exists() else None}
        bundle={"bundle_id":"bundle_"+uuid.uuid4().hex,"schema_version":1,"release_candidate":candidate,"artifacts":artifacts,"normalized_evidence":{"calculation_receipts":receipts,"capability_receipts":[],"recovery_receipts":[]},"trust":{"signed":False,"reason":"RELEASE_SIGNING_UNAVAILABLE"}}
        bundle["bundle_sha256"]=hashlib.sha256(canonical(bundle)).hexdigest(); path=self.root/"reproducibility_bundles"/(bundle["bundle_id"]+".json");path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(bundle,indent=2),encoding="utf-8");return path
    def verify(self,path:Path)->dict[str,object]:
        try:
            data=json.loads(path.read_text(encoding="utf-8"),
                            object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            # parse_constant does not catch exponent overflow such as 1e999.
            json.dumps(data, allow_nan=False)
            if type(data) is not dict or data.get("schema_version") != 1:
                raise ValueError("unsupported bundle schema")
            if type(data.get("schema_version")) is not int or not isinstance(data.get("bundle_id"),str):
                raise ValueError("invalid bundle identity")
            digest=data.pop("bundle_sha256",None)
            if digest!=hashlib.sha256(canonical(data)).hexdigest():return {"verdict":"BUNDLE_HASH_MISMATCH"}
            artifacts, candidate, trust = data["artifacts"], data["release_candidate"], data["trust"]
            if not all(type(value) is dict for value in (artifacts,candidate,trust)):
                raise ValueError("invalid bundle objects")
            if artifacts.get("release_candidate") != hashlib.sha256(canonical(candidate)).hexdigest():
                return {"verdict":"BUNDLE_ARTIFACT_HASH_MISMATCH"}
            if type(candidate.get("payload")) is not dict or candidate.get("payload_sha256") != hashlib.sha256(canonical(candidate["payload"])).hexdigest():
                return {"verdict":"BUNDLE_RELEASE_HASH_MISMATCH"}
            if candidate.get("verdict") != candidate["payload"].get("verdict"):
                return {"verdict":"BUNDLE_RELEASE_VERDICT_MISMATCH"}
            if type(trust.get("signed")) is not bool:
                raise ValueError("invalid signature claim")
            if trust["signed"]:
                # A recomputable checksum and a claimed flag do not authenticate
                # a signer. No signature verifier is configured at this boundary.
                return {"verdict":"BUNDLE_SIGNATURE_UNVERIFIED","signature_verified":False}
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return {"verdict":"BUNDLE_INVALID"}
        return {"verdict":"BUNDLE_INTEGRITY_VERIFIED_UNSIGNED","bundle_id":data["bundle_id"],
                "signature_verified":False,"release_authority_verified":False}
    def reproduce_diprotic(self,path:Path)->dict[str,object]:
        verified=self.verify(path)
        if verified["verdict"] != "BUNDLE_INTEGRITY_VERIFIED_UNSIGNED":
            return {"verdict":"EVIDENCE_INCOMPLETE","reason":verified["verdict"]}
        # A portable, validated mapping from bundled inputs, implementation and
        # oracles to an execution is not implemented. Running an unrelated fixed
        # fixture cannot reproduce this bundle's results.
        return {"verdict":"REPRODUCTION_UNVERIFIED","reason":"BUNDLE_REPLAY_NOT_IMPLEMENTED",
                "semantic_hash_match":None,"oracle_verdicts_match":None,"provenance_complete":False}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key,value in pairs:
        if key in result: raise ValueError("duplicate JSON key")
        result[key]=value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("non-finite JSON constant")
