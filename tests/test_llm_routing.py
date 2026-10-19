from pathlib import Path

from fermion.cognitive.llm import GenerationStatus
from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig


class RecordingCortex:
    def __init__(self, answer: str | None = "Chemistry synthesis from structured FERMiON context.") -> None:
        self.answer, self.calls, self.config = answer, [], None
        self.last_status = GenerationStatus(True, True, False, False, None, 0, 0, "http://test")
    def interpret(self, text: str): self.calls.append(("interpret", text)); return {"source": "heuristic"}
    def verbalize(self, payload: dict):
        self.calls.append(("verbalize", payload))
        self.last_status = GenerationStatus(True, True, True, self.answer is not None, None if self.answer else "LLM_EMPTY_RESPONSE", 32, len(self.answer or ""), "http://test")
        return self.answer


def test_long_prompt_runs_cognition_and_passes_original_request_plus_structured_result(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path)); cortex = RecordingCortex(); runtime.language = cortex
    request = "Analyze a complex chemistry mechanism. " * 180
    result = runtime.process(request)
    verbalize = next(payload for call, payload in cortex.calls if call == "verbalize")
    assert result.response.startswith("Chemistry synthesis")
    assert verbalize["user_input"] == request
    assert "workspace" in verbalize["reasoning"]
    assert result.generation_status["success"] is True
    events = (tmp_path / "logs" / "runtime.log").read_text(encoding="utf-8")
    for event in ("REQUEST_RECEIVED", "COGNITION_QUARANTINED", "WORKSPACE_UPDATED", "LLM_REQUEST_STARTED", "FINAL_RESPONSE_COMPLETE"):
        assert event in events


def test_chemistry_request_with_execution_language_is_scientific_not_a_narrow_executor_action(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path)); cortex = RecordingCortex("Chemistry answer from Qwen synthesis."); runtime.language = cortex
    result = runtime.process("Solve this chemistry equilibrium problem, then actually execute code if a verified tool plan is available.")
    assert result.interpretation["intent"] == "scientific"
    assert "Chemistry answer" in result.response
    assert "action" not in result.reasoning
    assert any(call == "verbalize" for call, _ in cortex.calls)


def test_verbalizer_receives_evidence_policy_before_generation(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path)); cortex = RecordingCortex("Analytical result only; execution not verified."); runtime.language = cortex
    runtime.process("Analyze a chemistry equilibrium and create and execute a Python verification only if available.")
    payload = next(value for call, value in cortex.calls if call == "verbalize")
    assert payload["evidence_policy"]["code_execution"]["receipt_present"] is False
    assert payload["evidence_policy"]["code_execution"]["may_claim_executed"] is False
    assert payload["actions"]["requested"] == ["code_execution"]
    assert payload["actions"]["blocked"] == [{"action": "code_execution", "reason": "no_execution_evidence"}]


def test_unavailable_llm_returns_specific_diagnostic_not_legacy_fallback(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path)); runtime.language = RecordingCortex(answer=None)
    result = runtime.process("Hello")
    assert "LLM_EMPTY_RESPONSE" in result.response
    assert "configured local GGUF" not in result.response
    assert result.generation_status["failure_reason"] == "LLM_EMPTY_RESPONSE"
