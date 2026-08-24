"""Deterministic, receipt-backed numerical computations (never LLM output)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from types import MappingProxyType
from typing import Callable, Mapping
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _freeze(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class CalculationEvidence:
    """Immutable numerical receipt.  All mappings are read-only snapshots."""
    calculation_id: str
    problem_type: str
    input_parameters: Mapping[str, object]
    solver_name: str
    solver_version: str | None
    variables: Mapping[str, float]
    derived_values: Mapping[str, float]
    residuals: Mapping[str, float]
    tolerances: Mapping[str, float]
    convergence_status: str
    iterations: int
    bracket_or_initial_guess: Mapping[str, float]
    equations_or_constraint_ids: tuple[str, ...]
    passed_oracles: tuple[str, ...]
    failed_oracles: tuple[str, ...]
    calculation_hash: str
    started_at: str
    finished_at: str
    provenance_graph: Mapping[str, object] = field(default_factory=dict)
    lineage: Mapping[str, object] = field(default_factory=dict)
    sensitivity: Mapping[str, object] = field(default_factory=dict)

    # Compatibility accessors for the earlier small receipt shape.
    @property
    def converged(self) -> bool: return self.convergence_status == "converged"
    @property
    def solution(self) -> float | None: return self.variables.get("root")
    @property
    def derived(self) -> Mapping[str, float]: return self.derived_values
    @property
    def computation_hash(self) -> str: return self.calculation_hash
    @property
    def inputs(self) -> Mapping[str, object]: return self.input_parameters
    @property
    def solver(self) -> str: return self.solver_name
    @property
    def passed(self) -> bool: return self.converged and not self.failed_oracles

    def to_dict(self) -> dict[str, object]:
        return {"calculation_id": self.calculation_id, "problem_type": self.problem_type,
                "input_parameters": dict(self.input_parameters), "solver_name": self.solver_name,
                "solver_version": self.solver_version, "variables": dict(self.variables),
                "derived_values": dict(self.derived_values), "residuals": dict(self.residuals),
                "tolerances": dict(self.tolerances), "convergence_status": self.convergence_status,
                "iterations": self.iterations, "bracket_or_initial_guess": dict(self.bracket_or_initial_guess),
                "equations_or_constraint_ids": list(self.equations_or_constraint_ids),
                "passed_oracles": list(self.passed_oracles), "failed_oracles": list(self.failed_oracles),
                "passed_oracles_all": self.passed, "calculation_hash": self.calculation_hash,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "provenance_graph": dict(self.provenance_graph), "lineage": dict(self.lineage),
                "sensitivity": dict(self.sensitivity),
                "certification_status": "verified" if self.passed else "unverified"}


def provenance_complete(graph: Mapping[str, object]) -> bool:
    """Require each derived value to trace input → constraint → solved variable → oracle."""
    nodes = {str(item.get("id")): item for item in graph.get("nodes", []) if isinstance(item, dict)}
    edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    derived = [node_id for node_id, item in nodes.items() if item.get("kind") == "derived_value"]
    if not derived: return True  # Scalar root receipts may have no derived user-facing values.
    incoming: dict[str, list[dict[str, object]]] = {}
    outgoing: dict[str, list[dict[str, object]]] = {}
    for edge in edges:
        incoming.setdefault(str(edge.get("to")), []).append(edge); outgoing.setdefault(str(edge.get("from")), []).append(edge)
    for value_id in derived:
        solved = [str(edge.get("from")) for edge in incoming.get(value_id, []) if edge.get("relation") == "derives"]
        if not solved or not all(nodes.get(item, {}).get("kind") == "solved_variable" for item in solved): return False
        constraints = [str(edge.get("from")) for variable in solved for edge in incoming.get(variable, []) if edge.get("relation") == "constrains"]
        if not constraints or not all(nodes.get(item, {}).get("kind") == "constraint" for item in constraints): return False
        inputs = [str(edge.get("from")) for constraint in constraints for edge in incoming.get(constraint, []) if edge.get("relation") == "parameterizes"]
        if not inputs or not any(nodes.get(item, {}).get("kind") == "parameter" for item in inputs): return False
        if not any(edge.get("relation") == "verified_by" and str(edge.get("from")) in constraints and nodes.get(str(edge.get("to")), {}).get("kind") == "oracle" for edge in edges): return False
    return True


def with_lineage(child: CalculationEvidence, *, parent: CalculationEvidence, relation_type: str,
                 changed_inputs: Mapping[str, Mapping[str, float]], model_constraint_hash: str) -> CalculationEvidence:
    """Link a newly solved child receipt; certification cannot exceed a parent dependency."""
    if relation_type not in {"counterfactual_of", "sensitivity_of"}: raise ValueError("unsupported evidence relation")
    lineage = _freeze({"relation_type": relation_type, "parent_calculation_id": parent.calculation_id,
                       "changed_inputs": dict(changed_inputs), "model_constraint_hash": model_constraint_hash,
                       "parent_certified": parent.passed})
    passed, failed = child.passed_oracles, child.failed_oracles
    if not parent.passed and "dependency_parent_unverified" not in failed:
        failed = (*failed, "dependency_parent_unverified")
    return replace(child, lineage=lineage, passed_oracles=passed, failed_oracles=failed)


def evaluate_oracles(*, residuals: Mapping[str, float], tolerances: Mapping[str, float],
                     nonnegative: Mapping[str, float] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Generic absolute/relative residual and non-negativity oracle evaluator."""
    passed: list[str] = []; failed: list[str] = []
    for name, value in residuals.items():
        oracle = name
        tolerance = tolerances.get(name)
        if tolerance is None:
            continue
        (passed if math.isfinite(value) and abs(value) <= tolerance else failed).append(oracle)
    for name, value in (nonnegative or {}).items():
        oracle = f"nonnegative:{name}"
        (passed if math.isfinite(value) and value >= 0 else failed).append(oracle)
    return tuple(passed), tuple(failed)


class ScalarRootSolver:
    """Validated scalar nonlinear solver: SciPy brentq when installed, bisection otherwise."""
    version = "1"

    def solve(self, function: Callable[[float], float], *, lower: float, upper: float,
              equation_id: str, inputs: Mapping[str, object], residual_tolerance: float = 1e-12,
              max_iterations: int = 256, problem_type: str = "scalar_nonlinear_root") -> CalculationEvidence:
        started = _utc_now(); lower_value, upper_value = function(lower), function(upper)
        bracket = {"lower": lower, "upper": upper}
        base = {"problem_type": problem_type, "input_parameters": dict(inputs), "solver_tolerance": residual_tolerance,
                "bracket": bracket, "equations": [equation_id]}
        digest = hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        def receipt(*, solver: str, status: str, iterations: int, root: float | None, root_residual: float) -> CalculationEvidence:
            residuals = {"root": root_residual, "bracket_lower": lower_value, "bracket_upper": upper_value}
            passed, failed = evaluate_oracles(residuals={"root": root_residual}, tolerances={"root": residual_tolerance}) if status == "converged" else ((), ("bracket_validation" if status == "invalid_bracket" else "convergence",))
            return CalculationEvidence("calc_" + uuid.uuid4().hex, problem_type, _freeze(inputs), solver, self.version,
                _freeze({"root": root} if root is not None else {}), _freeze({}), _freeze(residuals), _freeze({"root": residual_tolerance}), status,
                iterations, _freeze(bracket), (equation_id,), passed, failed, digest, started, _utc_now())
        if not all(math.isfinite(value) for value in (lower_value, upper_value)) or lower_value * upper_value > 0:
            return receipt(solver="bracket_validation", status="invalid_bracket", iterations=0, root=None, root_residual=math.nan)
        if lower_value == 0: return receipt(solver="bracket_validation", status="converged", iterations=0, root=lower, root_residual=0.0)
        if upper_value == 0: return receipt(solver="bracket_validation", status="converged", iterations=0, root=upper, root_residual=0.0)
        try:
            from scipy.optimize import brentq  # type: ignore
            root, info = brentq(function, lower, upper, xtol=residual_tolerance, rtol=4*math.ulp(1.0), maxiter=max_iterations, full_output=True)
            value = function(root)
            return receipt(solver="scipy.optimize.brentq", status="converged" if info.converged and abs(value) <= residual_tolerance else "nonconverged", iterations=info.iterations, root=root, root_residual=value)
        # SciPy raises RuntimeError when a deliberately tiny iteration budget is
        # exhausted.  That is a normal nonconvergence outcome, so fall through
        # to the deterministic bisection path and emit a receipt rather than
        # leaking a library exception.
        except (ImportError, RuntimeError, ValueError):
            pass
        left, right, left_value = lower, upper, lower_value
        for iteration in range(1, max_iterations + 1):
            root = (left + right) / 2.0; value = function(root)
            if not math.isfinite(value): return receipt(solver="python.bisection", status="nonconverged", iterations=iteration, root=root, root_residual=value)
            if abs(value) <= residual_tolerance: return receipt(solver="python.bisection", status="converged", iterations=iteration, root=root, root_residual=value)
            if left_value * value <= 0: right = root
            else: left, left_value = root, value
        root = (left + right) / 2.0
        return receipt(solver="python.bisection", status="nonconverged", iterations=max_iterations, root=root, root_residual=function(root))
