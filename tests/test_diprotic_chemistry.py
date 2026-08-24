from fermion.cognitive.chemistry import solve_diprotic_acid, solve_diprotic_with_evidence
from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig

def test_diprotic_full_constraints_initial_solution() -> None:
    result = solve_diprotic_acid()
    assert abs(result.pH - 2.5682244) < 1e-6
    assert abs(result.charge_residual) < 1e-12
    assert abs(result.mass_residual) < 1e-12
    assert abs(result.ka1_residual) < 1e-12
    assert abs(result.ka2_residual) < 1e-12

def test_diprotic_full_constraints_with_sodium() -> None:
    result = solve_diprotic_acid(sodium=.005)
    assert abs(result.pH - 3.1283008) < 1e-6
    assert abs(result.charge_residual) < 1e-12

def test_runtime_routes_diprotic_audit_to_constraint_solver(tmp_path) -> None:
    result = CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Solve H2A diprotic acid with Ka1=1e-3, Ka2=1e-6 and enforce electroneutrality.")
    assert result.interpretation["intent"] == "diprotic_audit"
    assert "pH = 2.568224" in result.response
    assert "Python execution not claimed" in result.response
    assert len(result.calculation_evidence) == 2
    assert all(item.converged for item in result.calculation_evidence)
    assert result.calculation_evidence[0].derived["H"] > 0

def test_diprotic_receipt_persists_and_verifies_after_runtime_restart(tmp_path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    result = runtime.process("Solve H2A diprotic acid with Ka1=1e-3, Ka2=1e-6 and enforce electroneutrality.")
    receipt = result.calculation_evidence[0]
    verified = CognitiveRuntime(RuntimeConfig(root=tmp_path)).verify_calculation(receipt.calculation_id)
    assert verified and verified["receipt"]["calculation_hash"] == receipt.calculation_hash

def test_diprotic_receipt_has_full_oracle_contract() -> None:
    _, receipt = solve_diprotic_with_evidence()
    assert receipt.passed
    assert not receipt.failed_oracles
    assert abs(receipt.residuals["charge_balance"]) < 1e-10
    assert set(("mass_balance", "charge_balance", "relative_ka1", "relative_ka2")).issubset(receipt.passed_oracles)

def test_verbalizer_cannot_alter_certified_diprotic_numbers(tmp_path, monkeypatch) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    monkeypatch.setattr(runtime.language, "verbalize", lambda _: "pH = 99.0")
    result = runtime.process("Solve H2A diprotic acid with Ka1=1e-3, Ka2=1e-6 and enforce electroneutrality.")
    assert "pH = 2.568224" in result.response
    assert "99.0" not in result.response
