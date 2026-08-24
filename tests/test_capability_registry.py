from fermion.cognitive.capability_registry import CapabilityRegistry
from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig

def test_registry_reports_live_loaded_capabilities(tmp_path) -> None:
    registry=CapabilityRegistry(tmp_path)
    record=registry.get("calculation_evidence")
    assert record and record.runtime_status == "active" and record.confidence == "authoritative"

def test_runtime_self_audit_is_read_only_and_exposes_gaps(tmp_path) -> None:
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path))
    audit=runtime.self_audit()
    assert audit["authority"] == "runtime_introspection"
    assert audit["mutation_permission"] is False
    assert "implemented_not_exposed" in audit["gaps"]

def test_explicit_self_inspection_bypasses_llm_inference(tmp_path) -> None:
    result=CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Before answering, query the live capability registry directly. What scientific capabilities are available?")
    assert result.interpretation["intent"] == "self_inspection"
    assert '"execution_evidence"' in result.response and '"memory_verification"' in result.response

def test_dependency_impact_and_blocked_health_propagate(tmp_path) -> None:
    registry=CapabilityRegistry(tmp_path, overrides={"calculation_evidence":"blocked"})
    assert "model_comparison" in registry.impact("calculation_evidence")["blocks"]
    health=registry.health()
    assert health["calculation_evidence"]["health_status"] == "blocked"
    assert health["diprotic_equilibrium"]["health_status"] == "blocked"
    assert health["model_comparison"]["health_status"] == "blocked"

def test_anomaly_diagnosis_and_recovery_are_evidence_grounded(tmp_path) -> None:
    registry=CapabilityRegistry(tmp_path, overrides={"calculation_evidence":"blocked"})
    for _ in range(3): registry.record_event("calculation_evidence","blocked","runtime_failure","ORACLE_FAILED","baseline_a")
    anomalies=registry.anomalies()
    assert anomalies[0]["state"] == "regression_confirmed"
    diagnosis=registry.diagnose("model_comparison")
    assert diagnosis["minimal_explanation_set"] == ["calculation_evidence"]
    plan=registry.recovery("calculation_evidence")
    assert "autonomous_source_edit" in plan["prohibited_actions"] and plan["mutation_permission"] is False

def test_arbitrary_coding_capabilities_are_not_inferred_from_receipts(tmp_path)->None:
    registry=CapabilityRegistry(tmp_path)
    assert registry.get("execution_evidence").runtime_status == "active"
    assert registry.get("code_execution").runtime_status == "unavailable"
    assert registry.get("workspace_file_write").availability_reason == "ARBITRARY_EXECUTION_NOT_IMPLEMENTED"
