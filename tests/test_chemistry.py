from fermion.cognitive.chemistry import n2o4_lint, solve_n2o4_equilibrium
from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig

def test_n2o4_equilibrium_has_verified_residual_and_volume_direction() -> None:
    result = solve_n2o4_equilibrium()
    assert abs(result.extent - 0.11494) < 1e-4
    assert result.residual < 1e-12
    assert result.volume_doubled_qp < result.kp

def test_n2o4_claim_lint_uses_registered_code_policy() -> None:
    audit = n2o4_lint()
    assert [item["verdict"] for item in audit] == ["ERROR", "PASS", "ERROR", "PASS"]
    assert {item["code"] for item in audit} == {"NO_REGISTERED_CODE"}

def test_n2o4_runtime_is_analytical_when_execution_has_no_receipt(tmp_path) -> None:
    result = CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Analyze N2O4 <=> 2 NO2 and actually execute code if available.")
    assert result.interpretation["intent"] == "chemistry_audit"
    assert "Analytical result only; execution not verified." in result.response
    assert "NO_REGISTERED_CODE" in result.response
