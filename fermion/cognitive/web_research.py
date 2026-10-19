"""Explicit, non-executing web retrieval with evidence receipts."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,uuid
from fermion.adapters.internet import InternetAdapter
from .evidence import WebEvidence
from urllib.parse import urlparse
def fetch_url(url:str,timeout:float=15)->WebEvidence:
    if urlparse(url).scheme not in {"https", "http"}:raise ValueError("WEB_URL_INVALID")
    try:
        url, raw, _, status = InternetAdapter.retrieve_public(url, 1_000_000, timeout)
        text=raw.decode("utf-8",errors="replace");state="WEB_VERIFIED"
    except Exception:
        text="";status=None;state="WEB_UNAVAILABLE"
    return WebEvidence("web_"+uuid.uuid4().hex,url,datetime.now(timezone.utc).isoformat(),status,hashlib.sha256(text.encode()).hexdigest(),text[:2000],state)

def assess_source(evidence:WebEvidence, claim:str="")->dict[str,object]:
    host=urlparse(evidence.url).hostname or ""; official=host.endswith((".gov",".edu")) or host in {"openai.com","docs.python.org","github.com"}
    lowered=evidence.content_excerpt.lower(); terms=[x for x in claim.lower().replace("?","").split() if len(x)>3]
    hits=[x for x in terms if x in lowered]; status="not_found" if claim and not hits else "supported" if claim and len(hits)>=max(1,len(terms)//2) else "ambiguous" if claim else "not_assessed"
    return {"evidence_id":evidence.evidence_id,"source_type":"primary" if official else "unknown","authority_status":"official" if official else "unknown","publication_date":None,"retrieved_at":evidence.retrieved_at,"content_hash":evidence.content_sha256,"claim_support":[{"claim":claim,"status":status,"excerpt_reference":"content_excerpt","matched_terms":hits}] if claim else [],"freshness":{"status":"unknown"},"inference_notice":"Retrieval and keyword matching do not establish truth or authority."}
