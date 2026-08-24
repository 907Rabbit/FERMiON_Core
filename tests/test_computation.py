from dataclasses import FrozenInstanceError
import pytest

from fermion.cognitive.computation import ScalarRootSolver, evaluate_oracles

def test_scalar_solver_produces_immutable_converged_evidence() -> None:
    evidence = ScalarRootSolver().solve(lambda x: x*x - 2, lower=0, upper=2, equation_id="sqrt2", inputs={}, residual_tolerance=1e-12)
    assert evidence.converged
    assert abs(evidence.solution**2 - 2) < 1e-12
    assert evidence.calculation_id.startswith("calc_")

def test_scalar_solver_rejects_impossible_bracket() -> None:
    evidence = ScalarRootSolver().solve(lambda x: x*x + 1, lower=-1, upper=1, equation_id="no_root", inputs={})
    assert not evidence.converged
    assert evidence.solution is None

def test_scalar_solver_reports_nonconvergence_when_iteration_budget_is_exhausted() -> None:
    evidence = ScalarRootSolver().solve(lambda x: x*x - 2, lower=0, upper=2, equation_id="limited", inputs={}, max_iterations=1, residual_tolerance=1e-30)
    assert evidence.convergence_status == "nonconverged"
    assert "convergence" in evidence.failed_oracles

def test_residual_oracle_rejects_out_of_tolerance_value() -> None:
    passed, failed = evaluate_oracles(residuals={"charge_balance": 1.1e-10}, tolerances={"charge_balance": 1e-10})
    assert not passed and failed == ("charge_balance",)

def test_calculation_evidence_cannot_be_reassigned() -> None:
    evidence = ScalarRootSolver().solve(lambda x: x - 1, lower=0, upper=2, equation_id="one", inputs={})
    with pytest.raises(FrozenInstanceError): evidence.iterations = 99
