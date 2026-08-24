from dataclasses import replace
import pytest

from fermion.cognitive.chemistry import counterfactual_diprotic_with_evidence, design_diprotic_ph_experiment, estimate_diprotic_ka1_from_ph, estimate_diprotic_ka1_ka2_from_ph, propagate_diprotic_pH_uncertainty, rank_diprotic_sensitivities, sensitivity_diprotic_pH, solve_diprotic_acid, solve_diprotic_with_evidence
from fermion.cognitive.computation import provenance_complete
from fermion.cognitive.scientific_ir import lower_diprotic_acid, normalized_semantics


PARAMS = {"concentration": .01, "ka1": 1e-3, "ka2": 1e-6, "kw": 1e-14, "sodium": .005}

def test_diprotic_generic_lowering_is_semantically_complete_and_equivalent() -> None:
    legacy = solve_diprotic_acid(**PARAMS)
    generic, receipt = solve_diprotic_with_evidence(**PARAMS)
    semantic = normalized_semantics(lower_diprotic_acid(**PARAMS))
    assert semantic["classification"] == ("chemistry", "diprotic_acid_speciation")
    assert {item[0] for item in semantic["constraint_semantics"]} >= {"mass_balance", "charge_balance", "Ka1", "Ka2", "Kw", "nonnegative"}
    assert abs(legacy.pH - generic.pH) < 1e-12
    assert receipt.passed and receipt.equations_or_constraint_ids[-2:] == ("Kw", "nonnegative")

@pytest.mark.parametrize("mutated", ["charge_balance", "Ka2", "Kw", "nonnegative"])
def test_golden_contract_rejects_missing_semantic_constraints(mutated: str) -> None:
    semantic = normalized_semantics(lower_diprotic_acid(**PARAMS))
    ids = {item[0] for item in semantic["constraint_semantics"]}
    assert mutated in ids  # A lowering that omitted this cannot match this golden contract.

def test_lowering_rejects_invalid_parameter_units_by_value_domain() -> None:
    with pytest.raises(ValueError):
        lower_diprotic_acid(**{**PARAMS, "ka2": 0.0})

def test_certified_diprotic_values_have_complete_provenance_paths() -> None:
    _, receipt = solve_diprotic_with_evidence(**PARAMS)
    assert provenance_complete(receipt.provenance_graph)
    assert "provenance_complete" in receipt.passed_oracles

def test_counterfactual_is_a_new_receipt_and_cannot_outrank_unverified_parent() -> None:
    _, baseline = solve_diprotic_with_evidence(**PARAMS)
    _, child = counterfactual_diprotic_with_evidence(baseline, changes={"Ka1": 2e-3})
    assert child.calculation_id != baseline.calculation_id
    assert child.lineage["relation_type"] == "counterfactual_of" and child.passed
    unverified_parent = replace(baseline, failed_oracles=("PROVENANCE_INCOMPLETE",))
    _, blocked = counterfactual_diprotic_with_evidence(unverified_parent, changes={"Ka1": 2e-3})
    assert not blocked.passed and "dependency_parent_unverified" in blocked.failed_oracles

def test_central_difference_sensitivity_has_certified_independent_perturbations() -> None:
    _, parent = solve_diprotic_with_evidence(**PARAMS)
    sensitivity = sensitivity_diprotic_pH(parent, input_parameter="Ka1")
    detail = sensitivity.sensitivity
    assert sensitivity.passed and sensitivity.lineage["relation_type"] == "sensitivity_of"
    assert detail["method"] == "central_finite_difference"
    assert detail["refinement"]["passed"] and detail["semantic_hash_match"]
    assert all(item["certified"] for item in detail["perturbations"].values())
    assert provenance_complete(sensitivity.provenance_graph)

def test_sensitivity_refuses_unverified_parent() -> None:
    _, parent = solve_diprotic_with_evidence(**PARAMS)
    with pytest.raises(ValueError):
        sensitivity_diprotic_pH(replace(parent, failed_oracles=("oracle_failed",)), input_parameter="Ka1")

def test_multi_parameter_ranking_consumes_only_certified_sensitivity_receipts() -> None:
    _, parent = solve_diprotic_with_evidence(**PARAMS)
    sensitivities, ranking = rank_diprotic_sensitivities(parent, parameters=("Ka1", "Ka2", "C", "Na"))
    entries = ranking.sensitivity["ranking"]["entries"]
    assert ranking.passed and len(entries) == 4
    assert [item["rank"] for item in entries] == [1, 2, 3, 4]
    assert all(item.passed for item in sensitivities)
    assert abs(entries[0]["normalized_sensitivity"]) >= abs(entries[-1]["normalized_sensitivity"])

def test_uncertainty_propagation_requires_certified_sensitivities_and_valid_covariance() -> None:
    _, parent = solve_diprotic_with_evidence(**PARAMS)
    sensitivities, _ = rank_diprotic_sensitivities(parent, parameters=("Ka1", "Ka2", "C"))
    uncertainty = propagate_diprotic_pH_uncertainty(parent, sensitivities, uncertainties={"Ka1": (2e-5, "mol/L"), "Ka2": (5e-8, "mol/L"), "C": (1e-4, "mol/L")})
    detail = uncertainty.sensitivity["uncertainty"]
    assert uncertainty.passed and detail["result"]["standard_uncertainty"] > 0
    assert sum(item["variance_fraction"] for item in detail["contribution_ranking"]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        propagate_diprotic_pH_uncertainty(parent, sensitivities, uncertainties={"Ka1": (2e-5, "mol/L"), "Ka2": (5e-8, "mol/L"), "C": (1e-4, "mol/L")}, covariance=[[1, 2], [2, 1]])

def test_single_parameter_inverse_estimation_reconstructs_certified_observation() -> None:
    reference, _ = solve_diprotic_with_evidence(**PARAMS)
    estimate = estimate_diprotic_ka1_from_ph(observed_ph=reference.pH, sigma_ph=1e-5, concentration=PARAMS["concentration"], ka2=PARAMS["ka2"], kw=PARAMS["kw"], sodium=PARAMS["sodium"])
    details = estimate.sensitivity["parameter_estimation"]
    assert estimate.passed
    assert estimate.lineage["relation_type"] == "inverse_of"
    assert estimate.variables["Ka1"] == pytest.approx(PARAMS["ka1"], rel=1e-6)
    assert details["validation"]["all_oracles_passed"]
    assert details["identifiability"]["classification"] == "uniquely_identifiable_local"

def test_two_parameter_inverse_certifies_independent_observation_set() -> None:
    observations = []
    for sodium in (0.0, .005, .01, .015):
        result, _ = solve_diprotic_with_evidence(concentration=.01, ka1=1e-3, ka2=1e-6, kw=1e-14, sodium=sodium)
        observations.append({"Na": sodium, "pH": result.pH, "sigma": 1e-4})
    fit = estimate_diprotic_ka1_ka2_from_ph(observations=observations, concentration=.01, kw=1e-14, initial=(8e-4, 2e-6), condition_limit=1e12)
    assert fit.passed
    assert fit.variables["Ka1"] == pytest.approx(1e-3, rel=1e-4)
    assert fit.variables["Ka2"] == pytest.approx(1e-6, rel=1e-3)

def test_two_parameter_inverse_marks_one_observation_rank_deficient() -> None:
    result, _ = solve_diprotic_with_evidence(concentration=.01, ka1=1e-3, ka2=1e-6, kw=1e-14, sodium=.005)
    fit = estimate_diprotic_ka1_ka2_from_ph(observations=[{"Na": .005, "pH": result.pH, "sigma": 1e-4}], concentration=.01, kw=1e-14, condition_limit=1e12)
    assert not fit.passed and "IDENTIFIABILITY_RANK_DEFICIENT" in fit.failed_oracles

def test_experimental_design_ranks_certified_fisher_information_candidates() -> None:
    observations=[]
    for sodium in (0., .005, .01, .015):
        result,_=solve_diprotic_with_evidence(concentration=.01,ka1=1e-3,ka2=1e-6,kw=1e-14,sodium=sodium)
        observations.append({"Na":sodium,"pH":result.pH,"sigma":1e-4})
    fit=estimate_diprotic_ka1_ka2_from_ph(observations=observations,concentration=.01,kw=1e-14,condition_limit=1e12)
    design=design_diprotic_ph_experiment(fit,candidates=[{"Na":0.},{"Na":.005},{"Na":.01},{"Na":.015}],measurement_sigma=1e-4)
    rows=design.sensitivity["experimental_design"]["candidates"]
    assert design.passed and rows[0]["score"] >= rows[-1]["score"]
    assert all(len(row["sensitivity_receipts"]) == 2 for row in rows)
