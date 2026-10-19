"""Local language-cortex boundary; FERMiON passes structured data across it."""
from __future__ import annotations
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import time
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from fermion.adapters.llama_cpp import (
    LlamaCppAdapter, LlamaCppConfig, LlamaServerRuntime,
    public_completion_text, strip_model_reasoning,
)
from .evidence_grounding import EvidenceClaimValidator, EvidenceEnvelope
from fermion.system_prompt import load_system_prompt
from .prompting import build_prompt, estimate_tokens, PromptBudgetError

@dataclass(frozen=True)
class GenerationStatus:
    configured: bool; healthy: bool; attempted: bool; success: bool; failure_reason: str | None
    estimated_prompt_tokens: int; response_length: int; endpoint: str | None
    http_status: int | None = None; generation_budget: int = 0; raw_output_chars: int = 0
    think_marker_found: bool = False; final_output_chars: int = 0; finish_reason: str = "unknown"; retry_count: int = 0
    llm_queue_ms: float | None = None; llm_generation_ms: float | None = None; timeout_stage: str | None = None
    request_ms: float = 0.0; prompt_build_ms: float = 0.0
    prompt_tokens: int | None = None; completion_tokens: int | None = None; total_tokens: int | None = None
    prompt_eval_ms: float | None = None; decode_ms: float | None = None
    usage_source: str = "unavailable"; backend: str | None = None; request_count: int = 0
    def to_dict(self) -> dict[str, object]: return asdict(self)


def extract_final_answer(text: str) -> tuple[str, str]:
    """Keep the legacy tuple shape without returning any private reasoning."""
    return "", strip_model_reasoning(text)


def contains_unverified_claim(text: str) -> bool:
    # Reject affirmative first-person/system claims, while allowing truthful limitations such as
    # "I did not execute code" or "no memory was retrieved".
    for match in re.finditer(r"\b(?:I|we|FERMiON|the system)\b[^.\n]{0,80}\b(executed|ran|saved|wrote to persistent memory|retrieved from persistent memory|verified)\b", text, re.I):
        prefix = match.group(0).lower()
        if not re.search(r"\b(no|not|never|cannot|can't|did not|without|unavailable|failed)\b", prefix): return True
    for match in re.finditer(r"\b(?:value|record|code|script|program|memory)\b[^.\n]{0,60}\bwas\s+(?:executed|saved|retrieved|verified)\b", text, re.I):
        if not re.search(r"\b(no|not|never|without|unavailable|failed)\b", match.group(0).lower()): return True
    # Headings/results that purport to report a tool run are disallowed unless FERMiON supplied a receipt.
    return bool(re.search(r"\b(python execution|executed computation|actual(?:ly)? execute[ds]?|root[- ]finding result|consistency checks?\s*:\s*.*\bpass|all checks pass)\b", text, re.I)) or bool(re.search(r"\b(?:evidence[_ ]id|memory[_ ]id)\s*[:=]\s*(?!unavailable|none|n/?a)", text, re.I))

class LocalLanguageCortex:
    def __init__(self, root: Path, model_path: str | None = None):
        self.config: LlamaCppConfig | None = None
        self.last_reasoning = ""
        self.last_raw_metadata: dict[str, object] = {}
        self.last_prompt_metadata: dict[str, object] = {}
        self.last_unsupported_claims: list[str] = []
        self.last_status = GenerationStatus(False, False, False, False, "LLM_NOT_CONFIGURED", 0, 0, None)
        local = root / "fermion.local.json"
        if local.is_file():
            try: self.config = LlamaCppConfig.from_file(local)
            except (OSError, ValueError, KeyError): pass
        if self.config and model_path:
            self.config = LlamaCppConfig(**{**self.config.to_dict(), "model_path": model_path})
        self.agent_bridge = None
        self.evidence_validator = EvidenceClaimValidator()
        self.system_prompt = load_system_prompt(root)
        self._request_model = None
        if self.config:
            try:
                from .agent_bridge import PydanticAgentBridge
                self.agent_bridge = PydanticAgentBridge(
                    self.config.endpoint,
                    self.config.model_identifier,
                    self.config.model_path,
                    self.system_prompt.content,
                    api_key=self.config.api_key,
                )
            except (ImportError, ValueError): pass

    def available(self) -> bool:
        return bool(self.config and self.config.endpoint and LlamaServerRuntime(self.config).health(.25))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return estimate_tokens(text)

    def _failure(self, reason: str, *, attempted: bool = False, request_ms: float = 0.0,
                 backend: str | None = None, estimated: int = 0, budget: int = 0,
                 http_status: int | None = None) -> None:
        self.last_status = GenerationStatus(
            bool(self.config), False, attempted, False, reason, estimated, 0,
            self.config.endpoint if self.config else None, http_status=http_status,
            generation_budget=budget, request_ms=request_ms, backend=backend,
            request_count=int(attempted), timeout_stage="transport" if reason == "LLM_TIMEOUT" else None)
        self.last_raw_metadata = {}

    @staticmethod
    def _usage_metadata(body: dict[str, Any]) -> dict[str, Any]:
        usage, timings = body.get("usage"), body.get("timings")
        usage = usage if isinstance(usage, dict) else {}
        timings = timings if isinstance(timings, dict) else {}
        def integer(value):
            return value if type(value) is int and value >= 0 else None
        def duration(value):
            return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
        prompt = integer(usage.get("prompt_tokens", usage.get("input_tokens")))
        completion = integer(usage.get("completion_tokens", usage.get("output_tokens")))
        return {"prompt_tokens": prompt, "completion_tokens": completion,
                "total_tokens": integer(usage.get("total_tokens")),
                "prompt_eval_ms": duration(timings.get("prompt_ms")),
                "decode_ms": duration(timings.get("predicted_ms")),
                "usage_source": "provider" if prompt is not None or completion is not None else "unavailable"}

    def _request(self, prompt: str, *, requested_tokens: int | None = None, retry_count: int = 0,
                 timeout_seconds: float | None = None) -> str | None:
        estimated = self._estimate_tokens(prompt + self.system_prompt.content) + 128
        if not self.config or not self.config.endpoint:
            self._failure("LLM_NOT_CONFIGURED", estimated=estimated)
            return None
        if not self.available():
            self._failure("LLM_UNHEALTHY", estimated=estimated)
            return None
        available = self.config.context_size - estimated
        budget = min(requested_tokens or self.config.max_tokens, available)
        if budget < 1:
            self._failure("LLM_CONTEXT_LIMIT", estimated=estimated)
            return None
        parsed = urllib.parse.urlsplit(self.config.endpoint)
        endpoint = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/v1/chat/completions", "", ""))
        request_data = {"messages": [{"role": "system", "content": self.system_prompt.content},
                                     {"role": "user", "content": prompt}],
                        "temperature": self.config.temperature, "max_tokens": budget}
        model = getattr(self, "_request_model", None) or self.config.model_identifier
        if model:
            request_data["model"] = model
        headers = {"Content-Type": "application/json"}
        if getattr(self.config, "api_key", None):
            headers["Authorization"] = "Bearer " + self.config.api_key
        request = urllib.request.Request(endpoint, json.dumps(request_data).encode("utf-8"), headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds or self.config.timeout_seconds) as response:
                http_status = response.status
                body = json.loads(response.read())
        except Exception as error:
            if not isinstance(error, (TimeoutError, OSError, ValueError)):
                raise
            reason = "LLM_TIMEOUT" if isinstance(error, TimeoutError) else "LLM_HTTP_ERROR"
            self._failure(reason, attempted=True, request_ms=(time.perf_counter()-started)*1000,
                          backend="http", estimated=estimated, budget=budget,
                          http_status=error.code if isinstance(error, urllib.error.HTTPError) else None)
            return None
        elapsed = (time.perf_counter()-started)*1000
        body = body if isinstance(body, dict) else {}
        choices = body.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        raw = public_completion_text(body)
        finish = str(choice.get("finish_reason") or body.get("stop_type") or "unknown")
        usage = self._usage_metadata(body)
        failure = "LLM_OUTPUT_TRUNCATED" if finish in {"length", "max_tokens"} else "LLM_EMPTY_RESPONSE" if not raw else None
        self.last_raw_metadata = {"http_status": http_status, "generation_budget": budget,
                                  "public_output_chars": len(raw), "finish_reason": finish}
        self.last_status = GenerationStatus(
            True, True, True, failure is None, failure, estimated, len(raw), endpoint,
            http_status=http_status, generation_budget=budget, raw_output_chars=len(raw),
            final_output_chars=len(raw), finish_reason=finish, retry_count=retry_count,
            request_ms=elapsed, llm_generation_ms=usage["decode_ms"], backend="http", request_count=1, **usage)
        return raw if failure is None else None

    def interpret(self, text: str) -> dict[str, Any]:
        """Explicit optional interpretation API; ordinary chat does not call it."""
        raw = self._request("Return JSON with intent, goal and entities for this text:\n" + text, requested_tokens=128)
        if raw is None:
            return {"source": "heuristic"}
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("invalid interpretation")
            return {"source": "llama.cpp", **payload}
        except ValueError:
            self._parse_failure("LLM_INVALID_INTERPRETATION", "", raw)
            return {"source": "heuristic"}

    def _generate(self, prompt: str, budget: int) -> str | None:
        """One backend and at most one generation request per turn, without hidden fallback."""
        timeout = getattr(self.config, "final_timeout_seconds", None) or self.config.timeout_seconds
        if self.agent_bridge is None:
            return self._request(prompt, requested_tokens=budget, timeout_seconds=timeout)
        started = time.perf_counter()
        try:
            answer = strip_model_reasoning(self.agent_bridge.synthesize(
                prompt, max_tokens=budget, timeout_seconds=timeout, temperature=self.config.temperature))
        except Exception as error:
            reason = "LLM_TIMEOUT" if "timeout" in type(error).__name__.lower() else "LLM_AGENT_ERROR"
            self._failure(reason, attempted=True, request_ms=(time.perf_counter()-started)*1000,
                          backend="pydantic_ai", estimated=self._estimate_tokens(prompt + self.system_prompt.content), budget=budget)
            return None
        metadata = getattr(self.agent_bridge, "last_metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        usage = self._usage_metadata({"usage": metadata})
        finish = str(metadata.get("finish_reason") or "unknown")
        failure = "LLM_OUTPUT_TRUNCATED" if finish in {"length", "max_tokens"} else "LLM_EMPTY_RESPONSE" if not answer else None
        self.last_status = GenerationStatus(
            True, True, True, failure is None, failure, self._estimate_tokens(prompt + self.system_prompt.content),
            len(answer), self.config.endpoint, generation_budget=budget, raw_output_chars=len(answer),
            final_output_chars=len(answer), finish_reason=finish, request_ms=(time.perf_counter()-started)*1000,
            backend="pydantic_ai", request_count=1, **usage)
        return answer if failure is None else None

    def _prepared_generation(self, cognitive_result: dict[str, Any]) -> str | None:
        self.last_reasoning = ""
        self.last_raw_metadata = {}
        self.last_prompt_metadata = {}
        if self.config is None:
            self._failure("LLM_NOT_CONFIGURED")
            return None
        started = time.perf_counter()
        budget = self.config.max_tokens
        try:
            packet = build_prompt(cognitive_result, input_token_budget=(self.config.context_size - budget
                                  - self._estimate_tokens(self.system_prompt.content) - 128))
        except (ValueError, TypeError) as error:
            self._failure("LLM_CONTEXT_LIMIT" if isinstance(error, PromptBudgetError) else "LLM_INVALID_CONTEXT")
            return None
        build_ms = (time.perf_counter()-started)*1000
        self.last_prompt_metadata = {"estimated_prompt_tokens": packet.estimated_tokens,
                                    "estimate_method": packet.estimate_method,
                                    "dropped_history_messages": packet.dropped_history_messages,
                                    "dropped_memory_items": packet.dropped_memory_items}
        answer = self._generate(packet.text, budget)
        self.last_status = replace(self.last_status, prompt_build_ms=build_ms)
        return answer

    def verbalize(self, cognitive_result: dict[str, Any], *, model_identifier: str | None = None) -> str | None:
        self._request_model = model_identifier
        try:
            answer = self._prepared_generation(cognitive_result)
        finally:
            self._request_model = None
        if answer is None:
            return None
        envelope = cognitive_result.get("evidence_envelope", {})
        epistemic = cognitive_result.get("epistemic_context", {})
        self.last_unsupported_claims = []
        if contains_unverified_claim(answer) or not self._evidence_valid(answer, envelope, epistemic):
            self._parse_failure("LLM_UNVERIFIED_CLAIM", "", answer)
            return self._unsupported_response(answer, envelope, epistemic)
        return answer

    def complete_direct(self, text: str, history: list[dict[str, str]] | None = None) -> str | None:
        """Same backend/config for evaluation, without FERMiON cognition or validators."""
        return self._prepared_generation({"user_input": text, "conversation_history": history or []})

    def _evidence_valid(self, answer: str, payload: object, epistemic_context: object = None) -> bool:
        if not isinstance(payload, dict):
            return not contains_unverified_claim(answer)
        try:
            envelope = EvidenceEnvelope.create(receipts=list(payload.get("receipts", [])), capabilities=list(payload.get("capabilities", [])))
            available = isinstance(epistemic_context, dict) and bool(epistemic_context.get("conversation_context_available"))
            result = self.evidence_validator.validate(answer, envelope, conversation_context_available=available)
            self.last_unsupported_claims = [item.text for item in result.unsupported_claims]
            return result.valid
        except (TypeError, ValueError):
            self.last_unsupported_claims = ["invalid_evidence_envelope"]
            return False

    def _unsupported_response(self, answer: str, payload: object, epistemic_context: object = None) -> str:
        # Deliberately return an explicit rejection rather than editing the LLM's
        # prose into an apparently verified claim.
        if not self.last_unsupported_claims:
            self._evidence_valid(answer, payload, epistemic_context)
        return "EVIDENCE_CLAIM_UNSUPPORTED: " + json.dumps(self.last_unsupported_claims)

    def _parse_success(self, prompt: str, raw: str) -> None:
        self.last_status = replace(self.last_status, success=True, failure_reason=None,
                                   response_length=len(raw), final_output_chars=len(strip_model_reasoning(raw)))

    def _parse_failure(self, reason: str, prompt: str, raw: str) -> None:
        self.last_status = replace(self.last_status, success=False, failure_reason=reason,
                                   response_length=len(raw), final_output_chars=0)

    @staticmethod
    def _concise_prompt(cognitive_result: dict[str, Any]) -> str:
        return build_prompt(cognitive_result, input_token_budget=8192).text
