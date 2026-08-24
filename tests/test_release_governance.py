from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.release_governance import ReleaseGovernor

def test_release_blocks_confirmed_regression_even_when_test_assets_exist(tmp_path) -> None:
    (tmp_path/"tests").mkdir(); (tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n",encoding="utf-8")
    registry=CapabilityRegistry(tmp_path)
    for _ in range(3): registry.record_event("calculation_evidence","degraded","runtime_failure","ORACLE_FAILED","base")
    result=ReleaseGovernor(tmp_path,registry).evaluate()
    assert result.verdict == "RELEASE_BLOCKED"
    assert "REGRESSION_CONFIRMED_UNRESOLVED" in result.blockers

def test_healthy_candidate_is_release_ready(tmp_path) -> None:
    (tmp_path/"tests").mkdir(); (tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n",encoding="utf-8")
    assert ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path)).evaluate().verdict == "RELEASE_READY"
