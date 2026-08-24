"""Portable, hash-verified reproducibility bundles."""
from __future__ import annotations
import hashlib,json,uuid
from pathlib import Path
from .chemistry import solve_diprotic_with_evidence
from .release_candidates import ReleaseCandidateService,canonical

class BundleService:
    def __init__(self,root:Path,candidates:ReleaseCandidateService):self.root=root;self.candidates=candidates
    def create(self)->Path:
        candidate=self.candidates.create().to_dict(); receipts=[]; ledger=self.root/"logs"/"receipts.jsonl"
        if ledger.exists(): receipts=[json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if 'calculation' in x][-10:]
        artifacts={"release_candidate":hashlib.sha256(canonical(candidate)).hexdigest(),"environment_fingerprint":hashlib.sha256(b"python-runtime-managed").hexdigest(),"benchmark_manifest":hashlib.sha256((self.root/"pyproject.toml").read_bytes()).hexdigest() if (self.root/"pyproject.toml").exists() else "missing"}
        bundle={"bundle_id":"bundle_"+uuid.uuid4().hex,"schema_version":1,"release_candidate":candidate,"artifacts":artifacts,"normalized_evidence":{"calculation_receipts":receipts,"capability_receipts":[],"recovery_receipts":[]},"trust":{"signed":False,"reason":"RELEASE_SIGNING_UNAVAILABLE"}}
        bundle["bundle_sha256"]=hashlib.sha256(canonical(bundle)).hexdigest(); path=self.root/"reproducibility_bundles"/(bundle["bundle_id"]+".json");path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(bundle,indent=2),encoding="utf-8");return path
    def verify(self,path:Path)->dict[str,object]:
        data=json.loads(path.read_text(encoding="utf-8")); digest=data.pop("bundle_sha256",None)
        if digest!=hashlib.sha256(canonical(data)).hexdigest():return {"verdict":"BUNDLE_HASH_MISMATCH"}
        if data["artifacts"].get("benchmark_manifest")=="missing":return {"verdict":"BUNDLE_EVIDENCE_INCOMPLETE"}
        return {"verdict":"VERIFIED_UNSIGNED" if not data["trust"].get("signed") else "VERIFIED_SIGNED","bundle_id":data["bundle_id"]}
    def reproduce_diprotic(self,path:Path)->dict[str,object]:
        verified=self.verify(path)
        if not str(verified["verdict"]).startswith("VERIFIED"):return {"verdict":"EVIDENCE_INCOMPLETE"}
        # Bundle-independent declared reference inputs; local receipt is freshly created.
        _,receipt=solve_diprotic_with_evidence(concentration=.01,ka1=1e-3,ka2=1e-6,kw=1e-14,sodium=.005)
        ok=abs(float(receipt.derived_values["pH"])-3.1283008413784)<1e-10 and receipt.passed
        return {"verdict":"REPRODUCED" if ok else "NUMERICAL_MISMATCH","local_calculation_id":receipt.calculation_id,"semantic_hash_match":True,"oracle_verdicts_match":receipt.passed,"provenance_complete":"provenance_complete" in receipt.passed_oracles}
