from fermion.cognitive.engineering import solve_simple_supported_beam
from fermion.cognitive.runtime import CognitiveRuntime,RuntimeConfig
def test_candidate_beam_receipt_has_consistent_required_and_candidate_values():
    r=solve_simple_supported_beam()
    assert r.passed
    assert r.derived_values["S_min_cm3"] == 186.66666666666666
    assert r.derived_values["I_min_cm4"] == 1920.0000000000002
    assert r.derived_values["candidate_Sx_cm3"] == 210
    assert r.derived_values["candidate_Ix_cm4"] == 2050
    assert abs(r.derived_values["sigma_max_Pa"]-133333333.3333)<1
    assert abs(r.derived_values["delta_total_mm"]-10.4065)<.001
    assert r.derived_values["closer_constraint"] == "deflection"
def test_stored_beam_receipt_is_reused_for_natural_language_lookup(tmp_path):
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path));first=runtime.process("Calculate the simply-supported beam.");receipt=first.calculation_evidence[0]
    second=runtime.process("Explain using the actual stored CalculationEvidence for the candidate simply-supported beam.")
    assert receipt.calculation_id in second.response and "1920.0 cm4" in second.response
    assert runtime.verify_calculation(receipt.calculation_id)
