"""Typed, non-LLM routing for deterministic scientific adapters."""
from __future__ import annotations

from dataclasses import dataclass
import re
import uuid
from typing import Any


_NUMBER = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)"
_FIELDS = {"concentration": ("c", "concentration"), "ka1": ("ka1",), "ka2": ("ka2",), "kw": ("kw",), "sodium": ("na", "na+", "sodium")}

@dataclass(frozen=True)
class ScientificRoute:
    request_id: str; detected_domain: str | None; detected_problem_class: str | None
    selected_skill: str | None; selected_adapter: str | None; computation_requested: bool
    computation_attempted: bool; calculation_id: str | None; calculation_status: str | None
    failure_reason: str | None; fallback_path: str; parameters: dict[str, float]
    requested_operation: str = "forward_solve"; selected_operation: str | None = None; selected_function: str | None = None
    fallback_used: bool = False; fallback_reason: str | None = None
    actual_invoked_function: str | None = None; response_template: str | None = None; operation_receipt_ids: tuple[str, ...] = ()
    interaction_mode: str = "conversation"; tool_required: bool = False; deterministic_operation_requested: bool = False; selected_tool: str | None = None; llm_synthesis_required: bool = True; interaction_reason: str = "default_natural_language"
    def metadata(self) -> dict[str, object]:
        result = {"request_id": self.request_id, "detected_domain": self.detected_domain,
                "detected_problem_class": self.detected_problem_class, "selected_skill": self.selected_skill,
                "selected_adapter": self.selected_adapter, "computation_requested": self.computation_requested,
                "computation_attempted": self.computation_attempted, "calculation_id": self.calculation_id,
                "calculation_status": self.calculation_status, "failure_reason": self.failure_reason,
                "fallback_path": self.fallback_path}
        result.update({"requested_operation": self.requested_operation, "selected_operation": self.selected_operation,
                       "selected_function": self.selected_function, "fallback_used": self.fallback_used, "fallback_reason": self.fallback_reason})
        result.update({"actual_invoked_function": self.actual_invoked_function, "response_template": self.response_template,
                       "operation_receipt_ids": list(self.operation_receipt_ids)})
        result.update({"interaction_mode": self.interaction_mode, "tool_required": self.tool_required,
                       "deterministic_operation_requested": self.deterministic_operation_requested, "selected_tool": self.selected_tool,
                       "llm_synthesis_required": self.llm_synthesis_required, "reason": self.interaction_reason})
        return result

def classify_interaction(text: str) -> tuple[str, bool, str]:
    lower=text.lower()
    if any(word in lower for word in ("capability registry", "live capability", "can you execute python", "what scientific capabilities")): return "self_inspection", False, "explicit_runtime_self_inspection"
    if "solve" in lower and any(term in lower for term in ("h2a", "ka1", "ka2", "diprotic")) and ("=" in lower or "enforce electroneutrality" in lower): return "scientific_calculation", True, "explicit_parameterized_solve"
    if any(word in lower for word in ("execute code", "run python", "create workspace/")): return "tool_action", True, "explicit_tool_action"
    if any(word in lower for word in ("fit ", "estimate ", "jointly infer", "inverse")): return "scientific_inverse", True, "explicit_inverse_request"
    if any(word in lower for word in ("design an experiment", "experiment design", "fisher information", "sequential active")): return "scientific_design", True, "explicit_design_request"
    if any(word in lower for word in ("calculate", "solve numerically", "solve the", "deterministic scientific solver", "compute ", "verify with evidence", "compare h1", "compare these two models quantitatively", "model discrimination", "hypothesis revision", "model-family", "sensitivity", "counterfactual", "uncertainty propagation")): return "scientific_calculation", True, "explicit_deterministic_request"
    if any(word in lower for word in ("explain", "why", "what would happen", "help me reason", "buffers resist")): return "scientific_explanation", False, "explanation_without_numeric_request"
    if any(word in lower for word in ("what do you think", "what can you do", "should learn next")): return "conceptual_reasoning", False, "conceptual_dialogue"
    if "remember" in lower or "recall" in lower: return "memory_query", False, "memory_query"
    if "plan" in lower: return "planning", False, "planning_request"
    return "conversation", False, "default_natural_language"

def detect_operation(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("model-family search", "model family", "family search")): return "model_family_search"
    if any(word in lower for word in ("hypothesis revision", "model revision", "add second dissociation", "model repair")): return "model_revision"
    if any(word in lower for word in ("competing hypotheses", "compare h1 and h2", "aic", "bic", "model discrimination", "not_discriminable", "separate models")): return "model_comparison_hypothesis_discrimination"
    if any(word in lower for word in ("sequential active", "add a new synthetic observation", "append a new observation", "stop_identifiable", "continue_experiments")): return "sequential_active_experiment"
    if all(word in lower for word in ("jointly infer", "ka1", "ka2", "design", "refit")): return "sequential_active_experiment"
    if any(word in lower for word in ("experiment design", "candidate naoh", "e-optimal", "fisher information")): return "experiment_design"
    if any(word in lower for word in ("jointly estimate", "estimate ka1 and ka2", "multi-parameter", "multiple synthetic pH")): return "inverse_multi_parameter"
    if any(word in lower for word in ("infer ka1", "estimate ka1", "inverse")): return "inverse_single_parameter"
    if "uncertainty" in lower: return "uncertainty_propagation"
    if "ranking" in lower and "sensitivity" in lower: return "sensitivity_ranking"
    if "sensitivity" in lower: return "sensitivity"
    if "counterfactual" in lower or "perturb" in lower: return "counterfactual"
    return "forward_solve"


def detect_scientific_route(text: str) -> ScientificRoute:
    lower = text.lower().replace("₂", "2").replace("₁", "1")
    request_id = "req_" + uuid.uuid4().hex
    interaction_mode, tool_required, interaction_reason = classify_interaction(text)
    chemistry = any(word in lower for word in ("acid", "chemistry", "equilibrium", "ka1", "ka2", "h2a", "diprotic", "naoh"))
    requested = any(word in lower for word in ("deterministic", "calculationevidence", "calculation evidence", "scientific solver", "verified")); operation = detect_operation(text)
    if not chemistry:
        return ScientificRoute(request_id, None, None, None, None, requested, False, None, None, "SCIENCE_DOMAIN_UNDETECTED", "normal_language", {}, operation, None, None, interaction_mode=interaction_mode, tool_required=tool_required, deterministic_operation_requested=tool_required, llm_synthesis_required=not tool_required, interaction_reason=interaction_reason)
    diprotic = any(word in lower for word in ("diprotic", "h2a", "ka1", "ka2"))
    if not diprotic:
        return ScientificRoute(request_id, "chemistry", "equilibrium_unspecified", "chemistry_equilibrium", None, requested, False, None, None, "PROBLEM_CLASS_UNDETECTED", "future_chemistry_adapter", {}, operation, None, None)
    parameters: dict[str, float] = {}
    for destination, names in _FIELDS.items():
        for name in names:
            match = re.search(r"\b" + re.escape(name) + r"\s*(?:=|:)?\s*" + _NUMBER, lower, re.I)
            if match:
                parameters[destination] = float(match.group(1)); break
    # The explicit request for the established, receipt-backed diprotic system selects its
    # documented canonical parameters. A partially supplied parameter set is never completed.
    canonical = ("diprotic" in lower or ("ka1" in lower and "ka2" in lower)) and not parameters and (requested or operation != "forward_solve")
    # The established audit shorthand supplies Ka1/Ka2 but omits the documented
    # C=0.01000 M and Kw=1e-14 defaults.  It is a canonical scenario, not an
    # invitation to invent a partially specified new system.
    shorthand_canonical = {"ka1", "ka2"}.issubset(parameters) and not ({"concentration", "kw"} & set(parameters))
    required = {"concentration", "ka1", "ka2", "kw"}
    if not (canonical or shorthand_canonical) and not required.issubset(parameters):
        return ScientificRoute(request_id, "chemistry", "diprotic_acid_speciation", "chemistry_equilibrium", "diprotic_acid", requested, False, None, None, "REQUIRED_PARAMETERS_MISSING", "calculation_unverified", parameters, operation, None, None, interaction_mode=interaction_mode, tool_required=tool_required, deterministic_operation_requested=tool_required, llm_synthesis_required=not tool_required, interaction_reason=interaction_reason)
    if canonical:
        parameters = {"concentration": .01000, "ka1": 1e-3, "ka2": 1e-6, "kw": 1e-14, "sodium": .00500}
    elif shorthand_canonical:
        parameters = {"concentration": .01000, "ka1": parameters["ka1"], "ka2": parameters["ka2"], "kw": 1e-14, "sodium": .00500}
    else:
        parameters.setdefault("sodium", .00500)
    functions = {"forward_solve": "diprotic_report_with_evidence", "counterfactual": "counterfactual_diprotic_with_evidence", "sensitivity": "sensitivity_diprotic_pH", "sensitivity_ranking": "rank_diprotic_sensitivities", "uncertainty_propagation": "propagate_diprotic_pH_uncertainty", "inverse_single_parameter": "estimate_diprotic_ka1_from_ph", "inverse_multi_parameter": "estimate_diprotic_ka1_ka2_from_ph", "experiment_design": "design_diprotic_ph_experiment", "sequential_active_experiment": "sequential_diprotic_active_experiment", "model_comparison_hypothesis_discrimination": "compare_diprotic_models", "model_revision": "revise_diprotic_hypothesis", "model_family_search": "search_diprotic_model_family"}
    return ScientificRoute(request_id, "chemistry", "diprotic_acid_speciation", "chemistry_equilibrium", "diprotic_acid", requested, False, None, None, None, "deterministic_adapter", parameters, operation, operation if tool_required else None, functions.get(operation) if tool_required else None, interaction_mode=interaction_mode, tool_required=tool_required, deterministic_operation_requested=tool_required, selected_tool=functions.get(operation) if tool_required else None, llm_synthesis_required=not tool_required, interaction_reason=interaction_reason)
