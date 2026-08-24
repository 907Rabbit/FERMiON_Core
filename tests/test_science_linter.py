from fermion.cognitive.science import lint_variational_claims, model_a_b_reference


def test_authoritative_variational_reference_preserves_f_k_distinction() -> None:
    reference = model_a_b_reference()
    assert "K = I" in reference["model_a"]
    assert "K = -Delta" in reference["model_b"]
    assert "mass is not generically conserved" in reference["model_a"]
    assert "mass is conserved" in reference["model_b"]


def test_required_diagnostic_codes_are_registered() -> None:
    assert {item["code"] for item in lint_variational_claims()} == {"PHI3201", "PHI3401", "PHI3501", "PHI3504"}
