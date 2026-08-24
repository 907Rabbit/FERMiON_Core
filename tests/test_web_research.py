import pytest
from fermion.cognitive.web_research import fetch_url,assess_source
from fermion.cognitive.evidence import WebEvidence
from fermion.cognitive.runtime import CognitiveRuntime,RuntimeConfig
def test_web_research_rejects_non_http_urls():
    with pytest.raises(ValueError): fetch_url("file:///unsafe")
def test_explicit_url_research_routes_to_web_evidence(tmp_path,monkeypatch):
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path))
    monkeypatch.setattr(runtime,"fetch_web",lambda url:{"evidence_id":"web_test","source_status":"WEB_VERIFIED","url":url,"content_sha256":"x","content_excerpt":"source text","retrieved_at":"now","status_code":200})
    result=runtime.process("Verify this source: https://example.com")
    assert "WebEvidence=web_test" in result.response
def test_assessment_does_not_promote_retrieval_to_authority():
    evidence=WebEvidence("web_x","https://example.com","now",200,"h","unrelated text","WEB_VERIFIED")
    assert assess_source(evidence,"claim that moon cheese")["claim_support"][0]["status"] == "not_found"
