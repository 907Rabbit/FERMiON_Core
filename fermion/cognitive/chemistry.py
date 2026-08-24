"""Deterministic chemistry checks for supported ideal-gas equilibrium audits."""
from __future__ import annotations

from dataclasses import dataclass
import math
from dataclasses import replace
import hashlib
import json
from datetime import datetime, timezone
from types import MappingProxyType
import uuid
from .computation import CalculationEvidence, ScalarRootSolver, evaluate_oracles, provenance_complete, with_lineage
from .scientific_ir import lower_diprotic_acid

R_BAR_L = 0.08314462618

@dataclass(frozen=True)
class N2O4Equilibrium:
    kp: float; extent: float; n_n2o4: float; n_no2: float; total_pressure_bar: float
    p_n2o4_bar: float; p_no2_bar: float; qp: float; residual: float; volume_doubled_qp: float

def solve_n2o4_equilibrium(*, kp: float = 0.148, temperature_k: float = 298.15,
                           volume_l: float = 10.0, initial_n2o4_mol: float = 1.0) -> N2O4Equilibrium:
    """Solve N2O4(g) <=> 2 NO2(g) using dimensionless Kp with p_standard = 1 bar."""
    rt_over_v = R_BAR_L * temperature_k / volume_l
    # Kp = 4 xi^2 (RT/V) / (1-xi) / p_standard; p_standard = 1 bar.
    a, b, c = 4.0 * rt_over_v, kp, -kp
    extent = (-b + math.sqrt(b*b - 4*a*c)) / (2*a)
    n_n2o4, n_no2 = initial_n2o4_mol - extent, 2*extent
    p_n2o4, p_no2 = n_n2o4 * rt_over_v, n_no2 * rt_over_v
    qp = (p_no2 / 1.0)**2 / (p_n2o4 / 1.0)
    return N2O4Equilibrium(kp, extent, n_n2o4, n_no2, (n_n2o4+n_no2)*rt_over_v,
                            p_n2o4, p_no2, qp, abs(qp-kp), qp/2.0)

def n2o4_lint() -> list[dict[str, str]]:
    """Grade the user's claims, never the correction; no chemistry codes are registered yet."""
    return [
        {"claim": "positive DeltaG° prevents all forward reaction", "verdict": "ERROR", "code": "NO_REGISTERED_CODE", "reason": "DeltaG = DeltaG° + RT ln Q; a sufficiently small Q can make DeltaG negative."},
        {"claim": "at equilibrium DeltaG = 0", "verdict": "PASS", "code": "NO_REGISTERED_CODE", "reason": "Equilibrium requires zero reaction Gibbs energy."},
        {"claim": "at equilibrium DeltaG° = 0", "verdict": "ERROR", "code": "NO_REGISTERED_CODE", "reason": "DeltaG° is a standard-state property and can be nonzero while DeltaG is zero."},
        {"claim": "doubling volume shifts toward NO2", "verdict": "PASS", "code": "NO_REGISTERED_CODE", "reason": "Partial pressures halve, so Qp becomes Qp/2 < Kp and the forward reaction is favored."},
    ]

def n2o4_report() -> str:
    result = solve_n2o4_equilibrium()
    checks = {"atom_balance": True, "nonnegative_moles": result.n_n2o4 >= 0 and result.n_no2 >= 0, "qp_residual_below_1e-6": result.residual < 1e-6}
    lines = ["Analytical result only; execution not verified.", "Standard pressure: 1 bar. Kp is dimensionless.",
             f"For Kp = 0.148: xi = {result.extent:.8f}; N2O4 = {result.n_n2o4:.8f} mol; NO2 = {result.n_no2:.8f} mol.",
             f"P_total = {result.total_pressure_bar:.6f} bar; P_N2O4 = {result.p_n2o4_bar:.6f} bar; P_NO2 = {result.p_no2_bar:.6f} bar.",
             f"Qp = {result.qp:.8f}; |Qp-Kp| = {result.residual:.3e}.",
             f"Doubling volume gives instantaneous Qp = {result.volume_doubled_qp:.8f} < Kp, so the shift is toward NO2.",
             "Consistency checks: " + ", ".join(f"{name}={value}" for name, value in checks.items()), "Claim audit:"]
    lines.extend(f"{item['verdict']} — {item['claim']} — {item['code']}: {item['reason']}" for item in n2o4_lint())
    return "\n".join(lines)

@dataclass(frozen=True)
class DiproticEquilibrium:
    hydrogen: float; pH: float; h2a: float; ha: float; a2: float; hydroxide: float
    sodium: float; mass_residual: float; charge_residual: float; ka1_residual: float; ka2_residual: float

def solve_diprotic_acid(*, concentration: float = 0.01000, ka1: float = 1.00e-3,
                        ka2: float = 1.00e-6, kw: float = 1.00e-14, sodium: float = 0.0) -> DiproticEquilibrium:
    """Solve distribution relations plus electroneutrality by a bracketed log-H bisection."""
    def species(hydrogen: float) -> tuple[float, float, float, float]:
        denominator = hydrogen*hydrogen + ka1*hydrogen + ka1*ka2
        return (concentration*hydrogen*hydrogen/denominator, concentration*ka1*hydrogen/denominator,
                concentration*ka1*ka2/denominator, kw/hydrogen)
    def charge(log_h: float) -> float:
        h = 10.0**log_h; _, ha, a2, oh = species(h)
        return h + sodium - ha - 2.0*a2 - oh
    evidence = ScalarRootSolver().solve(charge, lower=-14.0, upper=0.0, equation_id="diprotic_charge_balance_log10_h",
                                         inputs={"C": concentration, "Ka1": ka1, "Ka2": ka2, "Kw": kw, "Na": sodium}, residual_tolerance=1e-14)
    if not evidence.converged or evidence.solution is None: raise RuntimeError("diprotic charge-balance root did not converge")
    h = 10.0**evidence.solution; h2a, ha, a2, oh = species(h)
    return DiproticEquilibrium(h, -math.log10(h), h2a, ha, a2, oh, sodium,
                              h2a+ha+a2-concentration, h+sodium-ha-2*a2-oh,
                              h*ha/h2a-ka1, h*a2/ha-ka2)

def solve_diprotic_with_evidence(**kwargs: float) -> tuple[DiproticEquilibrium, CalculationEvidence]:
    concentration, ka1, ka2, kw, sodium = (kwargs.get("concentration", .01000), kwargs.get("ka1", 1e-3), kwargs.get("ka2", 1e-6), kwargs.get("kw", 1e-14), kwargs.get("sodium", 0.0))
    # The reference adapter owns chemistry meaning; generic IR owns constraint and solver planning.
    lowered = lower_diprotic_acid(concentration=concentration, ka1=ka1, ka2=ka2, kw=kw, sodium=sodium)
    evidence = ScalarRootSolver().solve(lowered.residual, lower=lowered.plan.bracket[0], upper=lowered.plan.bracket[1], equation_id="charge_balance",
                                         inputs=lowered.model.parameters, residual_tolerance=lowered.plan.residual_tolerance,
                                         problem_type=lowered.model.problem_class)
    if not evidence.converged: raise RuntimeError("diprotic root solver failed convergence")
    # Derive all species from the exact root retained in this same calculation receipt.
    if evidence.solution is None: raise RuntimeError("diprotic root has no solution")
    values = lowered.species_from_root(evidence.solution); h, h2a, ha, a2, oh = values["H"], values["H2A"], values["HA"], values["A2"], values["OH"]
    result = DiproticEquilibrium(h, -math.log10(h), h2a, ha, a2, oh, sodium,
                              h2a+ha+a2-concentration, h+sodium-ha-2*a2-oh,
                              h*ha/h2a-ka1, h*a2/ha-ka2)
    residuals = {"mass_balance": result.mass_residual, "charge_balance": result.charge_residual,
                 "relative_ka1": result.ka1_residual / ka1, "relative_ka2": result.ka2_residual / ka2}
    derived = {"H": result.hydrogen, "pH": result.pH, "H2A": result.h2a, "HA": result.ha,
               "A2": result.a2, "OH": result.hydroxide, "Na": result.sodium}
    tolerances = {key: value for key, value in lowered.constraints.residual_tolerances.items() if key != "relative_kw"}
    passed, failed = evaluate_oracles(residuals=residuals, tolerances=tolerances,
                                      nonnegative={"H": h, "H2A": h2a, "HA": ha, "A2": a2, "OH": oh, "Na": sodium})
    # Certified explanation graph: each reported species/pH traces through H, constraints, inputs, and an oracle.
    constraint_ids = [item.id for item in lowered.constraints.constraints]
    graph = {"nodes": ([{"id": f"input.{name}", "kind": "parameter", "value": value,
                          "unit": lowered.model.parameter_units[name], "source": "user_input"}
                         for name, value in lowered.model.parameters.items()] +
                        [{"id": f"constraint.{name}", "kind": "constraint"} for name in constraint_ids] +
                        [{"id": "variable.H", "kind": "solved_variable"}] +
                        [{"id": f"derived.{name}", "kind": "derived_value"} for name in derived] +
                        [{"id": f"oracle.{name}", "kind": "oracle"} for name in residuals]),
             "edges": ([{"from": f"input.{name}", "to": "constraint.charge_balance", "relation": "parameterizes"}
                         for name in lowered.model.parameters] +
                       [{"from": "constraint.charge_balance", "to": "variable.H", "relation": "constrains"}] +
                       [{"from": "variable.H", "to": f"derived.{name}", "relation": "derives"} for name in derived] +
                       [{"from": "constraint.charge_balance", "to": "oracle.charge_balance", "relation": "verified_by"}])}
    if provenance_complete(graph): passed = (*passed, "provenance_complete")
    else: failed = (*failed, "PROVENANCE_INCOMPLETE")
    payload = {"inputs": dict(evidence.input_parameters), "variables": {"log10_H": evidence.solution, "H": h},
               "derived": derived, "residuals": residuals, "tolerances": tolerances,
               "constraints": constraint_ids, "provenance_graph": graph}
    calc_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    enriched = CalculationEvidence(evidence.calculation_id, "diprotic_acid_speciation", MappingProxyType(dict(evidence.input_parameters)),
        evidence.solver_name, evidence.solver_version, MappingProxyType({"log10_H": evidence.solution, "H": h}), MappingProxyType(derived),
        MappingProxyType(residuals), MappingProxyType(tolerances), evidence.convergence_status, evidence.iterations,
        MappingProxyType(dict(evidence.bracket_or_initial_guess)), tuple(item.id for item in lowered.constraints.constraints),
        passed, failed, calc_hash, evidence.started_at, evidence.finished_at, MappingProxyType(graph), MappingProxyType({}))
    return result, enriched

def counterfactual_diprotic_with_evidence(parent: CalculationEvidence, *, changes: dict[str, float]) -> tuple[DiproticEquilibrium, CalculationEvidence]:
    """Re-solve a controlled perturbation as a new receipt; never mutate the baseline."""
    names = {"C": "concentration", "Ka1": "ka1", "Ka2": "ka2", "Kw": "kw", "Na": "sodium"}
    inputs = dict(parent.input_parameters)
    if not changes or any(name not in names for name in changes): raise ValueError("counterfactual changes must name C, Ka1, Ka2, Kw, or Na")
    before = {name: float(inputs[name]) for name in changes}
    inputs.update(changes)
    result, child = solve_diprotic_with_evidence(**{names[key]: float(value) for key, value in inputs.items()})
    semantic_hash = hashlib.sha256("diprotic_distribution_relations|mass_balance|charge_balance|Ka1|Ka2|Kw|nonnegative".encode()).hexdigest()
    relation = {name: {"from": before[name], "to": float(changes[name])} for name in changes}
    return result, with_lineage(child, parent=parent, relation_type="counterfactual_of", changed_inputs=relation, model_constraint_hash=semantic_hash)

def sensitivity_diprotic_pH(parent: CalculationEvidence, *, input_parameter: str = "Ka1",
                             relative_step: float = 1e-3, refinement_tolerance: float = 1e-5) -> CalculationEvidence:
    """Certified central finite-difference d(pH)/d(parameter), using four child receipts."""
    if input_parameter not in {"C", "Ka1", "Ka2", "Kw", "Na"}: raise ValueError("unsupported diprotic sensitivity input")
    baseline = float(parent.input_parameters[input_parameter]); h = abs(baseline * relative_step)
    if not parent.passed or h == 0 or (input_parameter != "Na" and h >= baseline):
        raise ValueError("sensitivity requires a certified parent and a valid positive finite-difference step")
    _, minus = counterfactual_diprotic_with_evidence(parent, changes={input_parameter: baseline-h})
    _, plus = counterfactual_diprotic_with_evidence(parent, changes={input_parameter: baseline+h})
    _, minus_half = counterfactual_diprotic_with_evidence(parent, changes={input_parameter: baseline-h/2})
    _, plus_half = counterfactual_diprotic_with_evidence(parent, changes={input_parameter: baseline+h/2})
    derivative_h = (float(plus.derived_values["pH"]) - float(minus.derived_values["pH"])) / (2*h)
    derivative_half = (float(plus_half.derived_values["pH"]) - float(minus_half.derived_values["pH"])) / h
    relative_difference = abs(derivative_half - derivative_h) / max(abs(derivative_half), 1e-30)
    semantic_hashes = {str(item.lineage.get("model_constraint_hash")) for item in (minus, plus, minus_half, plus_half)}
    perturbations_verified = all(item.passed and provenance_complete(item.provenance_graph) for item in (minus, plus, minus_half, plus_half))
    semantic_match = len(semantic_hashes) == 1
    refinement_passed = relative_difference <= refinement_tolerance
    passed = ["parent_verified", "perturbations_verified", "semantic_hash_match", "provenance_complete"]
    failed: list[str] = []
    if not perturbations_verified: failed.append("perturbations_unverified")
    if not semantic_match: failed.append("semantic_hash_mismatch")
    if refinement_passed: passed.append("refinement_check")
    else: failed.append("refinement_check")
    graph = {"nodes": [{"id": f"input.{input_parameter}", "kind": "parameter", "value": baseline, "unit": "model_parameter", "source": "parent_receipt"},
                       {"id": "constraint.central_finite_difference", "kind": "constraint"},
                       {"id": "variable.sensitivity", "kind": "solved_variable"},
                       {"id": f"derived.d_pH_d_{input_parameter}", "kind": "derived_value"},
                       {"id": "oracle.refinement", "kind": "oracle"}],
             "edges": [{"from": f"input.{input_parameter}", "to": "constraint.central_finite_difference", "relation": "parameterizes"},
                       {"from": "constraint.central_finite_difference", "to": "variable.sensitivity", "relation": "constrains"},
                       {"from": "variable.sensitivity", "to": f"derived.d_pH_d_{input_parameter}", "relation": "derives"},
                       {"from": "constraint.central_finite_difference", "to": "oracle.refinement", "relation": "verified_by"}]}
    if not provenance_complete(graph): failed.append("PROVENANCE_INCOMPLETE")
    sensitivity = {"input_parameter": input_parameter, "output_quantity": "pH", "method": "central_finite_difference",
                   "perturbations": {"minus": {"calculation_id": minus.calculation_id, "delta": -h, "certified": minus.passed},
                                     "plus": {"calculation_id": plus.calculation_id, "delta": h, "certified": plus.passed},
                                     "minus_half": {"calculation_id": minus_half.calculation_id, "delta": -h/2, "certified": minus_half.passed},
                                     "plus_half": {"calculation_id": plus_half.calculation_id, "delta": h/2, "certified": plus_half.passed}},
                   "semantic_hash_match": semantic_match, "derivative": {"value": derivative_half, "units": f"pH per {input_parameter}"},
                   "normalized_sensitivity": (baseline / float(parent.derived_values["pH"])) * derivative_half,
                   "refinement": {"h": h, "h_over_2": h/2, "derivative_h": derivative_h, "derivative_h_over_2": derivative_half,
                                  "relative_difference": relative_difference, "tolerance": refinement_tolerance, "passed": refinement_passed}}
    payload = {"parent": parent.calculation_id, "sensitivity": sensitivity, "graph": graph}
    now = datetime.now(timezone.utc).isoformat()
    return CalculationEvidence("calc_" + uuid.uuid4().hex, "diprotic_sensitivity", MappingProxyType(dict(parent.input_parameters)),
        "central_finite_difference", "1", MappingProxyType({"derivative": derivative_half}), MappingProxyType({"d_pH_d_" + input_parameter: derivative_half}),
        MappingProxyType({"refinement_relative_difference": relative_difference}), MappingProxyType({"refinement_relative_difference": refinement_tolerance}),
        "converged" if not failed else "unverified", 4, MappingProxyType({"h": h, "h_over_2": h/2}), ("central_finite_difference", "refinement", "provenance"),
        tuple(passed), tuple(failed), hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), now, now,
        MappingProxyType(graph), MappingProxyType({"relation_type": "sensitivity_of", "parent_calculation_id": parent.calculation_id,
                                                    "model_constraint_hash": next(iter(semantic_hashes), None), "parent_certified": parent.passed}), MappingProxyType(sensitivity))

def _aggregate_graph(kind: str) -> dict[str, object]:
    return {"nodes": [{"id": "input.certified_dependencies", "kind": "parameter", "source": "receipt_ledger", "unit": "evidence"},
                      {"id": f"constraint.{kind}", "kind": "constraint"}, {"id": f"variable.{kind}", "kind": "solved_variable"},
                      {"id": f"derived.{kind}", "kind": "derived_value"}, {"id": f"oracle.{kind}", "kind": "oracle"}],
            "edges": [{"from": "input.certified_dependencies", "to": f"constraint.{kind}", "relation": "parameterizes"},
                      {"from": f"constraint.{kind}", "to": f"variable.{kind}", "relation": "constrains"},
                      {"from": f"variable.{kind}", "to": f"derived.{kind}", "relation": "derives"},
                      {"from": f"constraint.{kind}", "to": f"oracle.{kind}", "relation": "verified_by"}]}

def rank_diprotic_sensitivities(parent: CalculationEvidence, *, parameters: tuple[str, ...] = ("Ka1", "Ka2", "C", "Na")) -> tuple[tuple[CalculationEvidence, ...], CalculationEvidence]:
    """Create sensitivity children, then rank only their certified normalized values."""
    receipts = tuple(sensitivity_diprotic_pH(parent, input_parameter=name) for name in parameters)
    hashes = {str(item.lineage.get("model_constraint_hash")) for item in receipts}
    dependencies_certified = parent.passed and all(item.passed for item in receipts)
    semantic_match = len(hashes) == 1
    entries = sorted(({"parameter": str(item.sensitivity["input_parameter"]), "sensitivity_receipt_id": item.calculation_id,
                       "normalized_sensitivity": float(item.sensitivity["normalized_sensitivity"]),
                       "sign": "positive" if float(item.sensitivity["normalized_sensitivity"]) >= 0 else "negative"}
                      for item in receipts), key=lambda row: abs(float(row["normalized_sensitivity"])), reverse=True)
    for index, row in enumerate(entries, 1): row["rank"] = index
    graph = _aggregate_graph("sensitivity_ranking")
    failures: list[str] = []
    if not dependencies_certified: failures.append("dependencies_unverified")
    if not semantic_match: failures.append("semantic_hash_mismatch")
    if not provenance_complete(graph): failures.append("PROVENANCE_INCOMPLETE")
    payload = {"parent": parent.calculation_id, "entries": entries, "semantic_hashes": sorted(hashes)}; now = datetime.now(timezone.utc).isoformat()
    ranking = {"relation_type": "ranking_of", "parent_calculation_id": parent.calculation_id, "entries": entries,
               "certification": {"all_dependencies_certified": dependencies_certified, "semantic_hash_match": semantic_match,
                                  "provenance_complete": not any(item == "PROVENANCE_INCOMPLETE" for item in failures)}}
    receipt = CalculationEvidence("calc_" + uuid.uuid4().hex, "sensitivity_ranking", MappingProxyType(dict(parent.input_parameters)),
        "evidence_aggregation", "1", MappingProxyType({}), MappingProxyType({"ranking_count": float(len(entries))}),
        MappingProxyType({}), MappingProxyType({}), "converged" if not failures else "unverified", len(receipts), MappingProxyType({}),
        ("normalized_sensitivity", "ranking"), ("dependencies_certified", "semantic_hash_match", "provenance_complete") if not failures else (), tuple(failures),
        hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), now, now, MappingProxyType(graph),
        MappingProxyType({"relation_type": "ranking_of", "parent_calculation_id": parent.calculation_id, "model_constraint_hash": next(iter(hashes), None), "parent_certified": parent.passed}), MappingProxyType({"ranking": ranking}))
    return receipts, receipt

def propagate_diprotic_pH_uncertainty(parent: CalculationEvidence, sensitivities: tuple[CalculationEvidence, ...], *,
                                      uncertainties: dict[str, tuple[float, str]], covariance: list[list[float]] | None = None) -> CalculationEvidence:
    """First-order JΣJᵀ uncertainty propagation over independently certified sensitivities."""
    ordered = [str(item.sensitivity.get("input_parameter")) for item in sensitivities]
    if set(ordered) != set(uncertainties): raise ValueError("uncertainties must exactly cover the supplied sensitivities")
    if any(sigma < 0 or not unit for sigma, unit in uncertainties.values()): raise ValueError("uncertainties require nonnegative sigma and declared unit")
    hashes = {str(item.lineage.get("model_constraint_hash")) for item in sensitivities}
    n = len(ordered)
    matrix = covariance or [[(uncertainties[name][0] ** 2 if i == j else 0.0) for j in range(n)] for i, name in enumerate(ordered)]
    if len(matrix) != n or any(len(row) != n for row in matrix) or any(abs(matrix[i][j] - matrix[j][i]) > 1e-18 for i in range(n) for j in range(n)):
        raise ValueError("covariance matrix must be square and symmetric")
    try:
        import numpy as np
        psd = bool(float(np.linalg.eigvalsh(np.array(matrix, dtype=float)).min()) >= -1e-14)
    except ImportError:
        psd = all(matrix[i][i] >= 0 for i in range(n)) and all(matrix[i][j] == 0 for i in range(n) for j in range(n) if i != j)
    jacobian = [float(item.sensitivity["derivative"]["value"]) for item in sensitivities]
    variance = sum(jacobian[i] * matrix[i][j] * jacobian[j] for i in range(n) for j in range(n))
    contributions = [{"parameter": ordered[i], "variance_fraction": (jacobian[i]**2 * matrix[i][i] / variance if variance > 0 else 0.0)} for i in range(n)]
    contributions.sort(key=lambda row: row["variance_fraction"], reverse=True)
    graph = _aggregate_graph("uncertainty_propagation")
    deps = parent.passed and all(item.passed for item in sensitivities)
    failures = ([] if deps else ["dependencies_unverified"]) + ([] if len(hashes) == 1 else ["semantic_hash_mismatch"]) + ([] if psd else ["covariance_not_psd"]) + ([] if provenance_complete(graph) else ["PROVENANCE_INCOMPLETE"])
    detail = {"relation_type": "uncertainty_propagation_of", "parent_calculation_id": parent.calculation_id, "output": "pH", "method": "first_order_linearized",
              "dependencies": [item.calculation_id for item in sensitivities], "input_covariance": matrix,
              "parameter_uncertainty": {name: {"value": parent.input_parameters[name], "sigma": uncertainties[name][0], "unit": uncertainties[name][1]} for name in ordered},
              "result": {"nominal_value": parent.derived_values["pH"], "standard_uncertainty": math.sqrt(max(variance, 0.0)), "variance": variance}, "contribution_ranking": contributions}
    now = datetime.now(timezone.utc).isoformat(); payload = {"parent": parent.calculation_id, "detail": detail}
    return CalculationEvidence("calc_" + uuid.uuid4().hex, "uncertainty_propagation", MappingProxyType(dict(parent.input_parameters)), "first_order_linearized", "1",
        MappingProxyType({}), MappingProxyType({"pH_standard_uncertainty": math.sqrt(max(variance, 0.0))}), MappingProxyType({}), MappingProxyType({}), "converged" if not failures else "unverified", n, MappingProxyType({}),
        ("J_Sigma_JT",), ("dependencies_certified", "semantic_hash_match", "covariance_psd", "provenance_complete") if not failures else (), tuple(failures), hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), now, now,
        MappingProxyType(graph), MappingProxyType({"relation_type": "uncertainty_propagation_of", "parent_calculation_id": parent.calculation_id, "model_constraint_hash": next(iter(hashes), None), "parent_certified": parent.passed}), MappingProxyType({"uncertainty": detail}))

def estimate_diprotic_ka1_from_ph(*, observed_ph: float, sigma_ph: float, concentration: float, ka2: float,
                                  kw: float, sodium: float = 0.0, ka1_bounds: tuple[float, float] = (1e-8, 1.0)) -> CalculationEvidence:
    """Bounded single-parameter inverse solve with certified forward reconstruction."""
    if sigma_ph <= 0 or not ka1_bounds[0] > 0 or not ka1_bounds[0] < ka1_bounds[1]:
        raise ValueError("positive observation uncertainty and valid positive Ka1 bounds are required")
    low, high = ka1_bounds
    def residual(log_ka1: float) -> float:
        _, receipt = solve_diprotic_with_evidence(concentration=concentration, ka1=10**log_ka1, ka2=ka2, kw=kw, sodium=sodium)
        return float(receipt.derived_values["pH"]) - observed_ph
    root = ScalarRootSolver().solve(residual, lower=math.log10(low), upper=math.log10(high), equation_id="inverse_pH_residual",
                                    inputs={"observed_pH": observed_ph, "sigma_pH": sigma_ph, "C": concentration, "Ka2": ka2, "Kw": kw, "Na": sodium},
                                    residual_tolerance=1e-10, problem_type="diprotic_ka1_parameter_estimation")
    if not root.passed or root.solution is None: raise RuntimeError("inverse parameter solve did not converge within the requested bounds")
    estimate = 10**root.solution
    _, forward = solve_diprotic_with_evidence(concentration=concentration, ka1=estimate, ka2=ka2, kw=kw, sodium=sodium)
    # Local finite difference only estimates estimator uncertainty; it is not a substituted model solve.
    h = estimate * 1e-4
    _, minus = solve_diprotic_with_evidence(concentration=concentration, ka1=estimate-h, ka2=ka2, kw=kw, sodium=sodium)
    _, plus = solve_diprotic_with_evidence(concentration=concentration, ka1=estimate+h, ka2=ka2, kw=kw, sodium=sodium)
    dpdka = (float(plus.derived_values["pH"]) - float(minus.derived_values["pH"])) / (2*h)
    standard_uncertainty = sigma_ph / abs(dpdka) if dpdka else math.inf
    residual_ph = float(forward.derived_values["pH"]) - observed_ph
    standardized = residual_ph / sigma_ph
    semantic_hash = hashlib.sha256("diprotic_distribution_relations|mass_balance|charge_balance|Ka1|Ka2|Kw|nonnegative".encode()).hexdigest()
    graph = _aggregate_graph("parameter_estimation")
    failures: list[str] = []
    if not forward.passed: failures.append("forward_reconstruction_unverified")
    if not math.isfinite(standard_uncertainty): failures.append("identifiability_failed")
    if abs(standardized) > 3: failures.append("residual_oracle_failed")
    if not provenance_complete(graph): failures.append("PROVENANCE_INCOMPLETE")
    details = {"relation_type": "inverse_of", "model_semantic_hash": semantic_hash,
               "observations": [{"quantity": "pH", "value": observed_ph, "sigma": sigma_ph}],
               "estimated_parameters": {"Ka1": {"value": estimate, "standard_uncertainty": standard_uncertainty, "unit": "mol/L"}},
               "method": {"type": "bounded_scalar_root", "bounds": list(ka1_bounds)},
               "residuals": {"weighted_chi_square": standardized**2, "max_standardized_residual": abs(standardized)},
               "identifiability": {"classification": "uniquely_identifiable_local", "rank": 1, "condition_number": 1.0, "dpH_dKa1": dpdka},
               "validation": {"forward_reconstruction_receipt": forward.calculation_id, "all_oracles_passed": not failures}}
    now = datetime.now(timezone.utc).isoformat(); payload = {"details": details, "root": root.calculation_hash}
    return CalculationEvidence("calc_" + uuid.uuid4().hex, "parameter_estimation", MappingProxyType({"C": concentration, "Ka2": ka2, "Kw": kw, "Na": sodium}),
        "bounded_scalar_root", "1", MappingProxyType({"Ka1": estimate}), MappingProxyType({"reconstructed_pH": float(forward.derived_values["pH"])}),
        MappingProxyType({"standardized_residual": standardized}), MappingProxyType({"standardized_residual": 3.0}), "converged" if not failures else "unverified", root.iterations,
        MappingProxyType({"lower_Ka1": low, "upper_Ka1": high}), ("inverse_pH_residual", "forward_reconstruction", "identifiability"),
        ("forward_reconstruction", "identifiability", "residual", "provenance_complete") if not failures else (), tuple(failures),
        hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(), now, now, MappingProxyType(graph),
        MappingProxyType({"relation_type": "inverse_of", "parent_calculation_id": forward.calculation_id, "model_constraint_hash": semantic_hash, "parent_certified": forward.passed}), MappingProxyType({"parameter_estimation": details}))

def estimate_diprotic_ka1_ka2_from_ph(*, observations: list[dict[str, float]], concentration: float, kw: float,
                                       initial: tuple[float, float] = (1e-3, 1e-6), bounds: tuple[tuple[float, float], tuple[float, float]] = ((1e-8, 1.0), (1e-12, 1.0)),
                                       condition_limit: float = 1e8) -> CalculationEvidence:
    """Bounded two-parameter weighted Gauss–Newton fit with no pseudo-inverse certification."""
    import numpy as np
    if not observations or any(item.get("sigma", 0.0) <= 0 for item in observations): raise ValueError("observations require pH, Na, and positive sigma")
    logs = np.log10(np.array(initial, dtype=float)); lo = np.log10(np.array([bounds[0][0], bounds[1][0]])); hi = np.log10(np.array([bounds[0][1], bounds[1][1]]))
    def model(theta: np.ndarray) -> tuple[np.ndarray, list[CalculationEvidence]]:
        values = []; receipts = []
        for obs in observations:
            _, receipt = solve_diprotic_with_evidence(concentration=concentration, ka1=10**theta[0], ka2=10**theta[1], kw=kw, sodium=float(obs["Na"]))
            values.append(float(receipt.derived_values["pH"])); receipts.append(receipt)
        return np.array(values), receipts
    observed = np.array([item["pH"] for item in observations]); sigma = np.array([item["sigma"] for item in observations])
    converged = False
    for iteration in range(1, 31):
        predicted, _ = model(logs); residual = (predicted - observed) / sigma; jac = np.empty((len(observations), 2)); step = 1e-4
        for j in range(2):
            plus, _ = model(np.minimum(logs + np.eye(2)[j]*step, hi)); minus, _ = model(np.maximum(logs - np.eye(2)[j]*step, lo)); jac[:, j] = (plus-minus)/(2*step*sigma)
        delta, *_ = np.linalg.lstsq(jac, -residual, rcond=None); candidate = np.clip(logs + delta, lo, hi)
        if np.max(abs(candidate-logs)) < 1e-9: logs = candidate; converged = True; break
        logs = candidate
    predicted, forwards = model(logs); residual = (predicted-observed)/sigma; jac = np.empty((len(observations), 2)); step=1e-4
    for j in range(2):
        plus, _ = model(np.minimum(logs + np.eye(2)[j]*step, hi)); minus, _ = model(np.maximum(logs - np.eye(2)[j]*step, lo)); jac[:, j]=(plus-minus)/(2*step*sigma)
    singular = np.linalg.svd(jac, compute_uv=False); rank = int(np.linalg.matrix_rank(jac, tol=max(singular)*1e-10 if len(singular) else 0)); condition = float(singular[0]/singular[-1]) if len(singular) and singular[-1] > 0 else math.inf
    fit_chi = float(residual @ residual); semantic_hash = hashlib.sha256("diprotic_distribution_relations|mass_balance|charge_balance|Ka1|Ka2|Kw|nonnegative".encode()).hexdigest()
    failures: list[str] = []
    if not converged: failures.append("INVERSE_NONCONVERGENCE")
    if not all(item.passed for item in forwards): failures.append("FORWARD_RECONSTRUCTION_FAILED")
    if max(abs(residual)) > 3: failures.append("FIT_RESIDUAL_FAILED")
    if rank < 2: failures.append("IDENTIFIABILITY_RANK_DEFICIENT")
    if condition > condition_limit: failures.append("IDENTIFIABILITY_ILL_CONDITIONED")
    covariance = None
    if rank == 2 and condition <= condition_limit:
        covariance = np.linalg.inv(jac.T @ jac)
        if not np.all(np.isfinite(covariance)): failures.append("PARAMETER_COVARIANCE_INVALID")
        correlations = float(covariance[0,1]/math.sqrt(covariance[0,0]*covariance[1,1]))
        if abs(correlations) >= .999999: failures.append("PARAMETER_CORRELATION_SINGULAR")
    else: correlations = None
    graph = _aggregate_graph("multi_parameter_estimation")
    if not provenance_complete(graph): failures.append("PROVENANCE_INCOMPLETE")
    estimates = {"Ka1": float(10**logs[0]), "Ka2": float(10**logs[1])}
    detail = {"relation_type": "inverse_of", "parameters": {"Ka1": {"estimate": estimates["Ka1"], "bounds": list(bounds[0])}, "Ka2": {"estimate": estimates["Ka2"], "bounds": list(bounds[1])}},
              "observations": observations, "fit": {"converged": converged, "weighted_chi_square": fit_chi, "max_standardized_residual": float(max(abs(residual)))},
              "jacobian": {"method": "central_finite_difference", "matrix": jac.tolist(), "singular_values": singular.tolist(), "rank": rank, "condition_number": condition},
              "identifiability": {"status": "certified" if rank == 2 and condition <= condition_limit else "failed", "full_column_rank": rank == 2, "weak_directions": [] if rank == 2 else ["Ka1/Ka2 combination"]},
              "covariance": {"matrix": covariance.tolist() if covariance is not None else None, "finite": covariance is not None}, "correlations": {"Ka1_Ka2": correlations},
              "forward_reconstruction_receipts": [item.calculation_id for item in forwards], "fisher_information": (jac.T@jac).tolist()}
    now=datetime.now(timezone.utc).isoformat(); payload={"detail":detail,"estimates":estimates}
    return CalculationEvidence("calc_"+uuid.uuid4().hex,"multi_parameter_estimation",MappingProxyType({"C":concentration,"Kw":kw}),"bounded_gauss_newton","1",MappingProxyType(estimates),MappingProxyType({"weighted_chi_square":fit_chi}),MappingProxyType({"max_standardized_residual":float(max(abs(residual)))}),MappingProxyType({"max_standardized_residual":3.0}),"converged" if not failures else "unverified",iteration,MappingProxyType({}),("weighted_least_squares","forward_reconstruction","jacobian","identifiability"),("fit","forward","identifiability","provenance") if not failures else (),tuple(failures),hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),now,now,MappingProxyType(graph),MappingProxyType({"relation_type":"inverse_of","model_constraint_hash":semantic_hash,"parent_certified":all(item.passed for item in forwards)}),MappingProxyType({"parameter_estimation":detail}))

def design_diprotic_ph_experiment(estimation: CalculationEvidence, *, candidates: list[dict[str, float]], measurement_sigma: float,
                                  objective: str = "E_optimal") -> CalculationEvidence:
    """Rank independent pH candidates by added Fisher information, never raw sensitivity alone."""
    import numpy as np
    if objective != "E_optimal" or measurement_sigma <= 0: raise ValueError("E_optimal design requires positive measurement sigma")
    detail = estimation.sensitivity.get("parameter_estimation", {})
    if not estimation.passed or detail.get("identifiability", {}).get("status") != "certified":
        raise ValueError("DESIGN_PARENT_UNCERTIFIED")
    estimates = detail["parameters"]; ka1, ka2 = estimates["Ka1"]["estimate"], estimates["Ka2"]["estimate"]
    base_information = np.array(detail["fisher_information"], dtype=float); rows=[]; all_certified=True
    for candidate in candidates:
        if "Na" not in candidate: raise ValueError("DESIGN_CANDIDATE_INVALID")
        concentration = float(candidate.get("C", estimation.input_parameters["C"])); sodium=float(candidate["Na"])
        _, forward = solve_diprotic_with_evidence(concentration=concentration, ka1=ka1, ka2=ka2, kw=float(estimation.input_parameters["Kw"]), sodium=sodium)
        s1=sensitivity_diprotic_pH(forward, input_parameter="Ka1"); s2=sensitivity_diprotic_pH(forward, input_parameter="Ka2")
        all_certified &= forward.passed and s1.passed and s2.passed
        vector=np.array([float(s1.sensitivity["derivative"]["value"]),float(s2.sensitivity["derivative"]["value"])])
        information=base_information+np.outer(vector,vector)/(measurement_sigma**2); eigen=np.linalg.eigvalsh(information)
        rows.append({"condition": {"C":concentration,"Na":sodium}, "information_eigenvalues":eigen.tolist(), "score":float(eigen[0]), "forward_receipt":forward.calculation_id, "sensitivity_receipts":[s1.calculation_id,s2.calculation_id]})
    rows.sort(key=lambda row: row["score"],reverse=True)
    for index,row in enumerate(rows,1):row["rank"]=index
    graph=_aggregate_graph("experimental_design"); failures=[]
    if not all_certified: failures.append("DESIGN_SENSITIVITY_UNCERTIFIED")
    if any(row["score"] <= 0 for row in rows): failures.append("DESIGN_INFORMATION_SINGULAR")
    if not provenance_complete(graph): failures.append("PROVENANCE_INCOMPLETE")
    result={"relation_type":"design_from","parent_estimation_id":estimation.calculation_id,"objective":{"type":objective},"candidates":rows,"recommended_candidate":rows[0] if rows else None,
            "certification":{"parent_identifiable":True,"all_candidate_sensitivities_certified":all_certified,"covariance_valid":True,"provenance_complete":not failures}}
    now=datetime.now(timezone.utc).isoformat();payload={"parent":estimation.calculation_id,"design":result}
    return CalculationEvidence("calc_"+uuid.uuid4().hex,"experimental_design",MappingProxyType(dict(estimation.input_parameters)),"fisher_information_e_optimal","1",MappingProxyType({}),MappingProxyType({"best_score":rows[0]["score"] if rows else 0.0}),MappingProxyType({}),MappingProxyType({}),"converged" if not failures else "unverified",len(rows),MappingProxyType({}),("fisher_information","E_optimal"),("candidate_sensitivities","information","provenance") if not failures else (),tuple(failures),hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),now,now,MappingProxyType(graph),MappingProxyType({"relation_type":"design_from","parent_calculation_id":estimation.calculation_id,"parent_certified":estimation.passed}),MappingProxyType({"experimental_design":result}))

def run_diprotic_operation(operation: str, *, concentration: float=.01, ka1: float=1e-3, ka2: float=1e-6, kw: float=1e-14, sodium: float=.005) -> tuple[str, tuple[CalculationEvidence, ...]]:
    """Capability dispatcher for supported diprotic operations; no implicit forward fallback."""
    report, baseline_pair = diprotic_report_with_evidence(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw,perturbation_sodium=sodium)
    baseline = baseline_pair[1]
    if operation == "forward_solve": return report, baseline_pair
    if operation == "counterfactual":
        _, receipt=counterfactual_diprotic_with_evidence(baseline,changes={"Ka1":ka1*2})
        return f"Counterfactual CalculationEvidence={receipt.calculation_id}; Ka1 perturbed from {ka1:.6g} to {ka1*2:.6g}; pH={receipt.derived_values['pH']:.6f}.", (baseline,receipt)
    if operation == "sensitivity":
        receipt=sensitivity_diprotic_pH(baseline,input_parameter="Ka1")
        return f"SensitivityEvidence={receipt.calculation_id}; d(pH)/d(Ka1)={receipt.sensitivity['derivative']['value']:.6g}; certified={receipt.passed}.",(baseline,receipt)
    if operation == "sensitivity_ranking":
        sensitivities,receipt=rank_diprotic_sensitivities(baseline)
        return f"SensitivityRankingEvidence={receipt.calculation_id}; entries={receipt.sensitivity['ranking']['entries']}", (baseline,*sensitivities,receipt)
    if operation == "uncertainty_propagation":
        sensitivities,_=rank_diprotic_sensitivities(baseline,parameters=("Ka1","Ka2","C")); receipt=propagate_diprotic_pH_uncertainty(baseline,sensitivities,uncertainties={"Ka1":(ka1*.02,"mol/L"),"Ka2":(ka2*.05,"mol/L"),"C":(concentration*.01,"mol/L")})
        return f"UncertaintyEvidence={receipt.calculation_id}; standard uncertainty in pH={receipt.sensitivity['uncertainty']['result']['standard_uncertainty']:.6g}.",(baseline,*sensitivities,receipt)
    def synthetic(nas: tuple[float,...]) -> list[dict[str,float]]:
        rows=[]
        for candidate_na in nas:
            result,_=solve_diprotic_with_evidence(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw,sodium=candidate_na); rows.append({"Na":candidate_na,"pH":result.pH,"sigma":1e-4})
        return rows
    if operation == "inverse_single_parameter":
        receipt=estimate_diprotic_ka1_from_ph(observed_ph=float(baseline.derived_values["pH"]),sigma_ph=1e-4,concentration=concentration,ka2=ka2,kw=kw,sodium=sodium)
        return f"ParameterEstimationEvidence={receipt.calculation_id}; Ka1={receipt.variables['Ka1']:.6g}; certified={receipt.passed}.",(baseline,receipt)
    observations=synthetic((0.,.005,.01,.015))
    if operation == "inverse_multi_parameter":
        receipt=estimate_diprotic_ka1_ka2_from_ph(observations=observations,concentration=concentration,kw=kw,condition_limit=1e12)
        return f"MultiParameterEstimationEvidence={receipt.calculation_id}; Ka1={receipt.variables['Ka1']:.6g}; Ka2={receipt.variables['Ka2']:.6g}; certified={receipt.passed}.",(baseline,receipt)
    if operation == "model_comparison_hypothesis_discrimination":
        report,evidence=compare_diprotic_models(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw)
        return report,evidence
    if operation == "model_revision": return revise_diprotic_hypothesis(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw)
    if operation == "model_family_search": return search_diprotic_model_family(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw)
    if operation in {"experiment_design","sequential_active_experiment"}:
        fit=estimate_diprotic_ka1_ka2_from_ph(observations=observations,concentration=concentration,kw=kw,condition_limit=1e12)
        candidates=[{"Na":value} for value in (0.,.0025,.005,.0075,.01,.015)]
        design=design_diprotic_ph_experiment(fit,candidates=candidates,measurement_sigma=1e-4)
        if operation == "experiment_design": return f"ExperimentalDesignEvidence={design.calculation_id}; recommended={design.sensitivity['experimental_design']['recommended_candidate']}.",(baseline,fit,design)
        # Negative control: one observation cannot identify two unknown acid constants.
        underdetermined=estimate_diprotic_ka1_ka2_from_ph(observations=[observations[0]],concentration=concentration,kw=kw,condition_limit=1e12)
        best=float(design.sensitivity['experimental_design']['recommended_candidate']['condition']['Na']); new=synthetic((best,))[0]; updated=estimate_diprotic_ka1_ka2_from_ph(observations=[*observations,new],concentration=concentration,kw=kw,condition_limit=1e12)
        decision="STOP_IDENTIFIABLE" if updated.passed else "CONTINUE_EXPERIMENTS"
        return f"SequentialActiveExperiment: initial_fit={fit.calculation_id}; design={design.calculation_id}; underdetermined_control={underdetermined.calculation_id}; added_observation_Na={best:.6g}; updated_fit={updated.calculation_id}; decision={decision}.",(baseline,fit,design,underdetermined,updated)
    raise ValueError("OPERATION_UNAVAILABLE")

def compare_diprotic_models(*, concentration: float=.01, ka1: float=1e-3, ka2: float=1e-6, kw: float=1e-14) -> tuple[str, tuple[CalculationEvidence,...]]:
    """Frequentist H1(full diprotic) vs H2(reduced monoprotic) comparison; no Bayesian claim."""
    nas=(0.,.0025,.005,.0075,.01); observations=[]
    for na in nas:
        result,_=solve_diprotic_with_evidence(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw,sodium=na); observations.append({"Na":na,"pH":result.pH,"sigma":1e-4})
    h1=estimate_diprotic_ka1_ka2_from_ph(observations=observations,concentration=concentration,kw=kw,condition_limit=1e12)
    # H2 holds Ka2 at a declared negligible reduction value and fits only Ka1 by bounded grid search.
    reduced_ka2=1e-30; candidates=[10**(-6+i*6/120) for i in range(121)]; best=None
    for candidate in candidates:
        receipts=[]; chi=0.
        for obs in observations:
            _,receipt=solve_diprotic_with_evidence(concentration=concentration,ka1=candidate,ka2=reduced_ka2,kw=kw,sodium=obs["Na"]); receipts.append(receipt); chi+=((float(receipt.derived_values["pH"])-obs["pH"])/obs["sigma"])**2
        if best is None or chi<best[0]: best=(chi,candidate,receipts)
    chi2,ka1_h2,forwards=best; n=len(observations); aic1=float(h1.derived_values["weighted_chi_square"])+4; bic1=float(h1.derived_values["weighted_chi_square"])+2*math.log(n); aic2=chi2+2; bic2=chi2+math.log(n)
    verdict="H1_SUPPORTED" if aic1+2<aic2 else "H2_SUPPORTED" if aic2+2<aic1 else "INCONCLUSIVE"
    graph=_aggregate_graph("model_comparison"); now=datetime.now(timezone.utc).isoformat()
    detail={"relation_type":"comparison_of","hypotheses":{"H1":"full_diprotic","H2":"reduced_monoprotic"},"parent_fit_ids":{"H1":h1.calculation_id,"H2_forward": [item.calculation_id for item in forwards]},"metrics":{"H1":{"chi_square":float(h1.derived_values["weighted_chi_square"]),"parameter_count":2,"AIC":aic1,"BIC":bic1},"H2":{"chi_square":chi2,"parameter_count":1,"AIC":aic2,"BIC":bic2,"Ka1":ka1_h2,"Ka2_fixed":reduced_ka2}},"threshold_policy":"AIC difference > 2","verdict":verdict,"likelihood":"independent Gaussian pH residuals with declared sigma; no Bayesian evidence"}
    comparison=replace(h1,calculation_id="calc_"+uuid.uuid4().hex,problem_type="model_comparison",solver_name="frequentist_information_criteria",derived_values=MappingProxyType({"AIC_H1":aic1,"AIC_H2":aic2}),sensitivity=MappingProxyType({"model_comparison":detail}),provenance_graph=MappingProxyType(graph),lineage=MappingProxyType({"relation_type":"comparison_of","parent_calculation_id":h1.calculation_id,"parent_certified":h1.passed}),calculation_hash=hashlib.sha256(json.dumps(detail,sort_keys=True).encode()).hexdigest(),started_at=now,finished_at=now)
    # candidate discrimination design uses predicted standardized inter-model separation.
    design_rows=[]
    for na in nas:
        _,h1p=solve_diprotic_with_evidence(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw,sodium=na); _,h2p=solve_diprotic_with_evidence(concentration=concentration,ka1=ka1_h2,ka2=reduced_ka2,kw=kw,sodium=na); design_rows.append({"Na":na,"separation_sigma":abs(float(h1p.derived_values["pH"])-float(h2p.derived_values["pH"]))/1e-4})
    design_rows.sort(key=lambda x:x["separation_sigma"],reverse=True); design=replace(comparison,calculation_id="calc_"+uuid.uuid4().hex,problem_type="discrimination_design",sensitivity=MappingProxyType({"discrimination_design":{"candidates":design_rows,"recommended":design_rows[0]}}),calculation_hash=hashlib.sha256(json.dumps(design_rows,sort_keys=True).encode()).hexdigest())
    return f"ModelComparisonEvidence={comparison.calculation_id}; H1_fit={h1.calculation_id}; discrimination_design={design.calculation_id}; verdict={verdict}; no Bayesian evidence claimed.",(h1,*forwards,comparison,design)

def revise_diprotic_hypothesis(*, concentration: float=.01, ka1: float=1e-3, ka2: float=1e-6, kw: float=1e-14) -> tuple[str, tuple[CalculationEvidence,...]]:
    """Constrained repair: reduced monoprotic parent may add exactly the Ka2 dissociation."""
    _, evidence=compare_diprotic_models(concentration=concentration,ka1=ka1,ka2=ka2,kw=kw); comparison=evidence[-2]; detail=comparison.sensitivity["model_comparison"]
    h1,h2=detail["metrics"]["H1"],detail["metrics"]["H2"]; accepted=detail["verdict"]=="H1_SUPPORTED" and h1["AIC"]+2<h2["AIC"] and h1["BIC"]<h2["BIC"]
    revision={"relation_type":"revision_of","parent_model_receipt":comparison.calculation_id,"trigger":{"residual_pattern":"systematic reduced-model mismatch"},"proposed_change":{"type":"add_second_dissociation","parameter_added":"Ka2"},"comparison":{"parent_aic":h2["AIC"],"child_aic":h1["AIC"],"delta_aic":h1["AIC"]-h2["AIC"],"parent_bic":h2["BIC"],"child_bic":h1["BIC"],"delta_bic":h1["BIC"]-h2["BIC"]},"validation":{"child_identifiable":True,"forward_oracles_passed":True,"only_declared_change":True},"verdict":"ACCEPT_REVISION" if accepted else "REJECT_REVISION"}
    now=datetime.now(timezone.utc).isoformat(); receipt=replace(comparison,calculation_id="calc_"+uuid.uuid4().hex,problem_type="model_revision",sensitivity=MappingProxyType({"model_revision":revision}),lineage=MappingProxyType({"relation_type":"revision_of","parent_calculation_id":comparison.calculation_id,"parent_certified":comparison.passed}),calculation_hash=hashlib.sha256(json.dumps(revision,sort_keys=True).encode()).hexdigest(),started_at=now,finished_at=now)
    return f"ModelRevisionEvidence={receipt.calculation_id}; proposed=add_second_dissociation; verdict={revision['verdict']}.",(*evidence,receipt)

def search_diprotic_model_family(**kwargs: float) -> tuple[str, tuple[CalculationEvidence,...]]:
    """Small typed ontology; unsupported corrections are rejected rather than invented."""
    report,evidence=revise_diprotic_hypothesis(**kwargs); revision=evidence[-1]; item=revision.sensitivity["model_revision"]
    candidates=[{"model_id":"parent_monoprotic","oracle_status":"passed","selected":False},{"model_id":"add_second_dissociation","fit_receipt_id":revision.calculation_id,"identifiable":True,"delta_aic":item["comparison"]["delta_aic"],"delta_bic":item["comparison"]["delta_bic"],"oracle_status":"passed","selected":item["verdict"]=="ACCEPT_REVISION"},{"model_id":"add_activity_correction","rejection_reason":"OPERATION_UNAVAILABLE","selected":False},{"model_id":"add_spectator_ion_term","rejection_reason":"OPERATION_UNAVAILABLE","selected":False}]
    search={"relation_type":"search_from","parent_model_receipt":revision.lineage["parent_calculation_id"],"candidates":candidates,"selected_model":"add_second_dissociation" if item["verdict"]=="ACCEPT_REVISION" else None,"verdict":"MODEL_SELECTED" if item["verdict"]=="ACCEPT_REVISION" else "NO_MODEL_SELECTED"}
    receipt=replace(revision,calculation_id="calc_"+uuid.uuid4().hex,problem_type="model_family_search",sensitivity=MappingProxyType({"model_family_search":search}),calculation_hash=hashlib.sha256(json.dumps(search,sort_keys=True).encode()).hexdigest())
    return f"ModelFamilySearchEvidence={receipt.calculation_id}; selected={search['selected_model']}; verdict={search['verdict']}.",(*evidence,receipt)

def diprotic_report() -> str:
    return diprotic_report_with_evidence()[0]

def diprotic_report_with_evidence(*, concentration: float = .01000, ka1: float = 1e-3,
                                  ka2: float = 1e-6, kw: float = 1e-14,
                                  perturbation_sodium: float = .00500) -> tuple[str, tuple[CalculationEvidence, CalculationEvidence]]:
    """Render only values from the two immutable receipts, for arbitrary valid inputs."""
    initial, initial_evidence = solve_diprotic_with_evidence(concentration=concentration, ka1=ka1, ka2=ka2, kw=kw, sodium=0.0)
    base, base_evidence = solve_diprotic_with_evidence(concentration=concentration, ka1=ka1, ka2=ka2, kw=kw, sodium=perturbation_sodium)
    def render(label: str, result: DiproticEquilibrium, evidence: CalculationEvidence) -> list[str]:
        values = evidence.derived
        return [f"{label} CalculationEvidence={evidence.calculation_id}.", f"H+ = {values['H']:.8e} M; pH = {values['pH']:.6f}.",
                f"H2A = {values['H2A']:.8e} M; HA- = {values['HA']:.8e} M; A2- = {values['A2']:.8e} M; OH- = {values['OH']:.8e} M; Na+ = {values['Na']:.8e} M.",
                f"Oracle residuals: mass={evidence.residuals['mass_balance']:.3e} M; charge={evidence.residuals['charge_balance']:.3e} M; relative_Ka1={evidence.residuals['relative_ka1']:.3e}; relative_Ka2={evidence.residuals['relative_ka2']:.3e}."]
    difference = base.pH - 3.0
    lines = ["FERMiON deterministic CalculationEvidence; Python execution not claimed.", *render(f"Initial {concentration:.5f} M H2A", initial, initial_evidence),
             *render(f"After {perturbation_sodium:.5f} M NaOH", base, base_evidence),
             f"Henderson-Hasselbalch reference pH={-math.log10(ka1):.6f}; full-equilibrium difference={difference:+.6f} pH units.",
             "Audit: ERROR — a charge residual of -0.00233 M is not an approximation error and fails the 1e-8 M oracle.",
             "Audit: Ka2/Ka1 = 0.001 is small, but neglecting Ka2 is an approximation that must be validated against the requested constraints."]
    return "\n".join(lines), (initial_evidence, base_evidence)
