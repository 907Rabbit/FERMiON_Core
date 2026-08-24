from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig
from fermion.cognitive.scientific_routing import detect_scientific_route


LIVE_REQUEST = "Solve the diprotic-acid system using the deterministic scientific solver and return only verified CalculationEvidence values."

def test_live_natural_language_diprotic_request_routes_to_receipts(tmp_path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    result = runtime.process(LIVE_REQUEST)
    route = runtime.last_route_status()
    assert len(result.calculation_evidence) == 2
    assert all(item.passed for item in result.calculation_evidence)
    assert "pH = 2.568224" in result.response
    assert route["selected_adapter"] == "diprotic_acid"
    assert route["calculation_status"] == "verified"

def test_partial_diprotic_parameters_do_not_get_invented() -> None:
    route = detect_scientific_route("Solve H2A equilibrium with C=0.01 and Ka1=1e-3; use deterministic CalculationEvidence.")
    assert route.failure_reason == "REQUIRED_PARAMETERS_MISSING"
    assert route.computation_attempted is False

def test_nonchemistry_request_is_not_science() -> None:
    assert detect_scientific_route("Tell me a short joke.").failure_reason == "SCIENCE_DOMAIN_UNDETECTED"

def test_other_chemistry_does_not_silently_use_diprotic_adapter() -> None:
    route = detect_scientific_route("Solve a triprotic phosphate equilibrium with deterministic calculation evidence.")
    assert route.failure_reason == "PROBLEM_CLASS_UNDETECTED"
    assert route.selected_adapter is None

def test_operation_classifier_selects_distinct_capabilities() -> None:
    cases = {"Solve the diprotic acid deterministic sensitivity.": "sensitivity", "Jointly estimate Ka1 and Ka2 from multiple synthetic pH observations.": "inverse_multi_parameter", "Use Fisher information for diprotic experiment design.": "experiment_design", "Run a diprotic sequential active experiment with a new synthetic observation and STOP_IDENTIFIABLE.": "sequential_active_experiment"}
    for prompt, operation in cases.items():
        route = detect_scientific_route(prompt)
        assert route.selected_operation == operation and route.selected_function

def test_sequential_active_cli_route_does_not_return_basic_forward_response(tmp_path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    result = runtime.process("Jointly infer Ka1 and Ka2 from multiple synthetic pH observations for the diprotic acid, design at least five candidate NaOH conditions, append a new observation, refit, compare identifiability, and issue STOP_IDENTIFIABLE or CONTINUE_EXPERIMENTS.")
    assert "SequentialActiveExperiment" in result.response
    assert "Initial 0.01000 M H2A" not in result.response
    route = runtime.last_route_status()
    assert route["selected_operation"] == "sequential_active_experiment"
    assert route["actual_invoked_function"] == "sequential_diprotic_active_experiment"
    assert route["response_template"] == "sequential_active_experiment"
    assert len(route["operation_receipt_ids"]) >= 5
    assert "underdetermined_control=" in result.response

def test_model_comparison_dispatch_never_uses_forward_template(tmp_path) -> None:
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path))
    result=runtime.process("Compare H1 and H2 competing hypotheses for diprotic acid model discrimination using AIC or BIC and select next experiment to separate models.")
    assert "ModelComparisonEvidence=" in result.response and "Initial 0.01000 M H2A" not in result.response
    route=runtime.last_route_status()
    assert route["selected_operation"] == "model_comparison_hypothesis_discrimination"
    assert route["actual_invoked_function"] == "compare_diprotic_models"

def test_model_revision_and_family_search_dispatch_are_not_forward(tmp_path) -> None:
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path))
    result=runtime.process("Run a diprotic hypothesis revision: add second dissociation to the monoprotic model.")
    assert "ModelRevisionEvidence=" in result.response
    assert runtime.last_route_status()["actual_invoked_function"] == "revise_diprotic_hypothesis"
    result=runtime.process("Run a diprotic model-family search with add second dissociation.")
    assert "ModelFamilySearchEvidence=" in result.response
    assert runtime.last_route_status()["actual_invoked_function"] == "search_diprotic_model_family"

def test_interaction_mode_prevents_chemistry_terms_from_authorizing_solver(tmp_path) -> None:
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.process("Calculate the pH of this diprotic acid using deterministic evidence.")
    conversational=runtime.process("What do you think FERMiON should learn next after that diprotic calculation?")
    route=runtime.last_route_status()
    assert route["interaction_mode"] == "conceptual_reasoning" and not route["tool_required"]
    assert "Initial 0.01000 M H2A" not in conversational.response

def test_explanation_is_not_deterministic_calculation() -> None:
    route=detect_scientific_route("Explain why buffers resist pH change.")
    assert route.interaction_mode == "scientific_explanation" and not route.tool_required

def test_explicit_calculation_remains_tool_routed() -> None:
    route=detect_scientific_route("Calculate the pH of this diprotic acid using deterministic evidence.")
    assert route.interaction_mode == "scientific_calculation" and route.tool_required
