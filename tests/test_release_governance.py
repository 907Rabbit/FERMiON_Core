from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.release_governance import ReleaseGovernor

def test_release_blocks_confirmed_regression_even_when_test_assets_exist(tmp_path) -> None:
    (tmp_path/"tests").mkdir(); (tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n",encoding="utf-8")
    registry=CapabilityRegistry(tmp_path)
    for _ in range(3): registry.record_event("calculation_evidence","degraded","runtime_failure","ORACLE_FAILED","base")
    result=ReleaseGovernor(tmp_path,registry).evaluate()
    assert result.verdict == "RELEASE_BLOCKED"
    assert "REGRESSION_CONFIRMED_UNRESOLVED" in result.blockers

def test_test_directory_and_package_metadata_do_not_certify_a_release(tmp_path) -> None:
    (tmp_path/"tests").mkdir(); (tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n",encoding="utf-8")
    result = ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path)).evaluate()
    assert result.verdict == "RELEASE_BLOCKED"
    assert result.benchmarks["passed"] is False
    assert result.benchmarks["test_assets_present"] is True
    assert result.provenance["package_metadata_present"] is True
    assert result.provenance["manifest_valid"] is False
    assert result.provenance["hashes_valid"] is False
    assert result.provenance["consistency_valid"] is False
    assert "BENCHMARK_EVIDENCE_UNVERIFIED" in result.blockers
    assert "PROVENANCE_UNVERIFIED" in result.blockers


def test_passing_test_source_and_declared_versions_are_not_execution_evidence(tmp_path) -> None:
    (tmp_path/"tests").mkdir()
    (tmp_path/"tests"/"test_sample.py").write_text("def test_ok():\n    assert True\n",encoding="utf-8")
    (tmp_path/"pyproject.toml").write_text("[project]\nname='x'\n",encoding="utf-8")
    result = ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path)).evaluate({"language":"current"})
    assert result.verdict == "RELEASE_BLOCKED"
    assert result.benchmarks["passed"] is False


def test_missing_assets_remain_distinct_from_unverified_evidence(tmp_path) -> None:
    result = ReleaseGovernor(tmp_path,CapabilityRegistry(tmp_path)).evaluate()
    assert "BENCHMARK_EVIDENCE_MISSING" in result.blockers
    assert "PROVENANCE_INVALID" in result.blockers
