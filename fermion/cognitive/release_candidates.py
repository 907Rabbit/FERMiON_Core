"""Immutable release candidates and externally-authorized signature verification."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib,json,uuid
from pathlib import Path
from .release_governance import ReleaseGovernor

def canonical(value:object)->bytes:return json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()
@dataclass(frozen=True)
class ReleaseCandidateEvidence:
    candidate_id:str; payload:dict[str,object]; payload_sha256:str; verdict:str
    def to_dict(self)->dict[str,object]:return asdict(self)

class ReleaseCandidateService:
    def __init__(self,root:Path,governor:ReleaseGovernor):self.root=root;self.governor=governor
    def create(self)->ReleaseCandidateEvidence:
        ready=self.governor.evaluate().to_dict(); control=self.root/"pyproject.toml"; control_hash=hashlib.sha256(control.read_bytes()).hexdigest() if control.exists() else "unknown"
        payload={"schema_version":"1","versions":ready["versions"],"source_identity":{"control_program_hash":control_hash,"repository_hash":"unavailable_no_vcs"},"evidence":{"release_readiness":ready,"regression_report_ids":[],"recovery_receipt_ids":[]},"environment":{"python":"runtime-managed"},"verdict":ready["verdict"]}
        digest=hashlib.sha256(canonical(payload)).hexdigest();return ReleaseCandidateEvidence("rc_"+uuid.uuid4().hex,payload,digest,ready["verdict"])
    def verify(self,candidate:ReleaseCandidateEvidence, envelope:dict[str,object]|None=None, trusted_keys:dict[str,bytes]|None=None)->dict[str,object]:
        if hashlib.sha256(canonical(candidate.payload)).hexdigest()!=candidate.payload_sha256:return {"valid":False,"failure_reason":"RELEASE_HASH_MISMATCH"}
        if candidate.verdict=="RELEASE_BLOCKED":return {"valid":False,"failure_reason":"RELEASE_BLOCKED_BY_REGRESSION"}
        if envelope is None:return {"valid":False,"failure_reason":"RELEASE_SIGNATURE_MISSING"}
        key_id=str(envelope.get("key_id",""))
        if not trusted_keys or key_id not in trusted_keys:return {"valid":False,"failure_reason":"RELEASE_KEY_UNTRUSTED"}
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            import base64
            Ed25519PublicKey.from_public_bytes(trusted_keys[key_id]).verify(base64.b64decode(str(envelope["signature"])),canonical(candidate.payload))
        except ImportError:return {"valid":False,"failure_reason":"RELEASE_SIGNING_UNAVAILABLE"}
        except Exception:return {"valid":False,"failure_reason":"RELEASE_SIGNATURE_INVALID"}
        return {"valid":True,"failure_reason":None,"candidate_id":candidate.candidate_id}
