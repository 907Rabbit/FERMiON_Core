"""Local language-cortex boundary; FERMiON passes structured data across it."""
from __future__ import annotations
import json
import re
import urllib.error
import urllib.request
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fermion.adapters.llama_cpp import LlamaCppAdapter, LlamaCppConfig, LlamaServerRuntime
from .evidence_grounding import EvidenceClaimValidator, EvidenceEnvelope

@dataclass(frozen=True)
class GenerationStatus:
    configured: bool; healthy: bool; attempted: bool; success: bool; failure_reason: str | None
    estimated_prompt_tokens: int; response_length: int; endpoint: str | None
    http_status: int | None = None; generation_budget: int = 0; raw_output_chars: int = 0
    think_marker_found: bool = False; final_output_chars: int = 0; finish_reason: str = "unknown"; retry_count: int = 0
    llm_queue_ms: float = 0.0; llm_generation_ms: float = 0.0; timeout_stage: str | None = None
    def to_dict(self) -> dict[str, object]: return asdict(self)


def extract_final_answer(text: str) -> tuple[str, str]:
    """Split Qwen Thinking output without ever treating thought text as a reply."""
    marker = "</think>"
    if marker not in text:
        return "", ""
    reasoning, answer = text.rsplit(marker, 1)
    return reasoning.replace("<think>", "").strip(), answer.strip()


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
        if self.config:
            try:
                from .agent_bridge import PydanticAgentBridge
                self.agent_bridge = PydanticAgentBridge(self.config.endpoint, self.config.model_path)
            except (ImportError, ValueError): pass

    def available(self) -> bool:
        return bool(self.config and self.config.endpoint and LlamaServerRuntime(self.config).health(.25))

    @staticmethod
    def _estimate_tokens(text: str) -> int: return max(1, (len(text) + 3) // 4)

    def _request(self, prompt: str, *, requested_tokens: int | None = None, retry_count: int = 0,
                 timeout_seconds: float | None = None) -> str | None:
        if not self.config or not self.config.endpoint:
            self.last_status = GenerationStatus(False, False, False, False, "LLM_NOT_CONFIGURED", self._estimate_tokens(prompt), 0, None); return None
        healthy = self.available()
        if not healthy:
            self.last_status = GenerationStatus(True, False, False, False, "LLM_UNHEALTHY", self._estimate_tokens(prompt), 0, self.config.endpoint); return None
        estimated = self._estimate_tokens(prompt); reserve = 128; available = self.config.context_size - estimated - reserve
        if available < 128:
            self.last_status = GenerationStatus(True, True, False, False, "LLM_CONTEXT_LIMIT", estimated, 0, self.config.endpoint); return None
        budget = min(requested_tokens or self.config.max_tokens, available)
        endpoint = self.config.endpoint.replace("/completion", "/v1/chat/completions")
        clean_prompt = prompt.replace("[INST]", "").replace("[/INST]", "").strip()
        payload = json.dumps({"messages": [{"role": "system", "content": "You are FERMiON's local language layer. Keep private reasoning separate from the final answer."}, {"role": "user", "content": clean_prompt}], "temperature": self.config.temperature, "max_tokens": budget}).encode("utf-8")
        request = urllib.request.Request(endpoint, payload, {"Content-Type": "application/json"})
        started = time.perf_counter()
        request_timeout = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                http_status = response.status; body = json.loads(response.read())
        except TimeoutError:
            self.last_status = GenerationStatus(True, True, True, False, "LLM_TIMEOUT", estimated, 0, self.config.endpoint, generation_budget=budget, retry_count=retry_count, llm_generation_ms=(time.perf_counter()-started)*1000, timeout_stage="http_client_generation"); return None
        except urllib.error.HTTPError as error:
            self.last_status = GenerationStatus(True, True, True, False, "LLM_HTTP_ERROR", estimated, 0, self.config.endpoint, http_status=error.code, generation_budget=budget, retry_count=retry_count, llm_generation_ms=(time.perf_counter()-started)*1000); return None
        except (OSError, ValueError, json.JSONDecodeError):
            self.last_status = GenerationStatus(True, True, True, False, "LLM_HTTP_ERROR", estimated, 0, self.config.endpoint, generation_budget=budget, retry_count=retry_count, llm_generation_ms=(time.perf_counter()-started)*1000); return None
        choice = body.get("choices", [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = str(message.get("content") or choice.get("text") or body.get("content") or "")
        thought = str(message.get("reasoning_content") or "")
        raw = f"<think>{thought}</think>{content}" if thought else content
        finish = str(choice.get("finish_reason") or body.get("stop_type") or body.get("stop_reason") or "unknown")
        self.last_raw_metadata = {"http_status": http_status, "generation_budget": budget, "raw_output_chars": len(raw), "finish_reason": finish, "response_keys": sorted(body.keys()), "chat_endpoint": endpoint}
        if not raw.strip():
            self.last_status = GenerationStatus(True, True, True, False, "LLM_EMPTY_RESPONSE", estimated, 0, endpoint, http_status=http_status, generation_budget=budget, raw_output_chars=0, finish_reason=finish, retry_count=retry_count, llm_generation_ms=(time.perf_counter()-started)*1000); return None
        self.last_status = GenerationStatus(True, True, True, True, None, estimated, len(raw), endpoint, http_status=http_status, generation_budget=budget, raw_output_chars=len(raw), think_marker_found="</think>" in raw, finish_reason=finish, retry_count=retry_count, llm_generation_ms=(time.perf_counter()-started)*1000)
        return raw

    def interpret(self, text: str) -> dict[str, Any]:
        # A strict JSON boundary gives the cognitive backend machine-readable linguistic input.
        prompt = "[INST] Return only valid JSON after reasoning: {intent:string, goal:string, entities:[string]}. Interpret this user text: " + text[:1500] + " [/INST]"
        try:
            raw = self._request(prompt, requested_tokens=128)
            if raw is None: return {"source": "heuristic"}
            reasoning, final = extract_final_answer(raw)
            self.last_reasoning = reasoning
            if not final: self._parse_failure("LLM_THINKING_TRUNCATED", prompt, raw); return {"source": "heuristic"}
            payload = json.loads(final[final.find("{"):final.rfind("}")+1]); self._parse_success(prompt, raw)
            return {"source": "llama.cpp", **payload}
        except (ValueError, json.JSONDecodeError): return {"source": "heuristic"}

    def verbalize(self, cognitive_result: dict[str, Any]) -> str | None:
        if self.config is None:
            return None
        envelope_payload = cognitive_result.get("evidence_envelope", {})
        evidence_note = ("Read the EvidenceEnvelope and ClaimManifest as immutable, authoritative grounding. Verbalize only claims authorized by the ClaimManifest; do not add, upgrade, or audit claims. Never create, alter, infer, or reinterpret receipt IDs, hashes, commands, paths, exit codes, capability states, timestamps, or certification results. Label an interpretive conclusion as 'Inference:' when it goes beyond supplied evidence. "
                         "Every evidence-sensitive statement must be exactly supported by the EvidenceEnvelope. "
                         "Read evidence_policy and actions in the FERMiON result as authoritative. Never claim an action was "
                         "executed, written, saved, retrieved, verified, measured, tested, or persisted unless the corresponding "
                         "receipt is present and explicitly authorizes it. If a requested action was not completed, say so plainly "
                         "and continue with the analytical portion where possible. ")
        prompt = ("[INST] You are FERMiON's language output layer. FERMiON has already performed memory retrieval, "
                  "cognitive processing, planning, scientific analysis, and metacognitive evaluation. Convert the supplied "
                  "result into a clear, coherent final answer. Return only the answer after your reasoning. Do not reveal "
                  "thought process, discuss JSON, describe retrieved memories unless relevant, second-guess FERMiON, or output "
                  "<think> content. " + evidence_note + "\nORIGINAL USER REQUEST:\n" + str(cognitive_result.get("user_input", ""))[:4500] + "\nFERMiON STRUCTURED RESULT:\n" + json.dumps(cognitive_result, default=str)[:4000] + "\nCLAIM MANIFEST (READ ONLY):\n" + json.dumps(cognitive_result.get("claim_manifest", {}), default=str)[:3500] + "\nEVIDENCE ENVELOPE (READ ONLY):\n" + json.dumps(envelope_payload, default=str)[:5000] + "\n[/INST]")
        # Primary interface: PydanticAI agent over the local OpenAI-compatible llama.cpp API.
        # It receives no execution authority; FERMiON continues to own all tools and receipts.
        if self.agent_bridge is not None:
            try:
                compact_agent_prompt=("Produce a concise user-facing answer. Do not invent facts, actions, receipts, "
                                      "or measurements. State missing inputs plainly.\nUSER:\n"+str(cognitive_result.get("user_input",""))[:2200]+
                                      "\nFERMiON CONTEXT:\n"+json.dumps(cognitive_result.get("reasoning",{}),default=str)[:1800]+
                                      "\nREAD-ONLY CLAIM MANIFEST:\n"+json.dumps(cognitive_result.get("claim_manifest",{}),default=str)[:2200]+
                                      "\nREAD-ONLY EVIDENCE ENVELOPE:\n"+json.dumps(envelope_payload,default=str)[:3000])
                answer=self.agent_bridge.synthesize(compact_agent_prompt, max_tokens=min(1024, self.config.max_tokens))
                if answer and not contains_unverified_claim(answer) and self._evidence_valid(answer, envelope_payload, cognitive_result.get("epistemic_context", {})): return answer
                if answer:
                    return self._unsupported_response(answer, envelope_payload, cognitive_result.get("epistemic_context", {}))
            except Exception:
                pass
        try:
            raw = self._request(prompt, timeout_seconds=getattr(self.config, "final_timeout_seconds", None) or self.config.timeout_seconds)
            if raw is None:
                # Some Thinking-model/template combinations emit immediate EOS on a large structured prompt.
                # Retry once with the same FERMiON result but a compact final-answer instruction.
                if self.last_status.failure_reason not in {"LLM_EMPTY_RESPONSE", "LLM_CONTEXT_LIMIT"}: return None
                prompt = self._concise_prompt(cognitive_result)
                raw = self._request(prompt, retry_count=1, timeout_seconds=getattr(self.config, "final_timeout_seconds", None) or self.config.timeout_seconds)
                if raw is None: return None
            reasoning, answer = extract_final_answer(raw)
            self.last_reasoning = reasoning
            if not answer:
                self._parse_failure("LLM_THINKING_TRUNCATED", prompt, raw)
                if self.last_status.retry_count >= 1: return None
                concise = self._concise_prompt(cognitive_result)
                raw = self._request(concise, retry_count=1, timeout_seconds=getattr(self.config, "final_timeout_seconds", None) or self.config.timeout_seconds)
                if raw is None: return None
                reasoning, answer = extract_final_answer(raw); self.last_reasoning = reasoning
                if not answer: self._parse_failure("LLM_THINKING_TRUNCATED", concise, raw); return None
                self._parse_success(concise, raw)
            # No receipt is supplied to ordinary chat; claims of completed external action are rejected.
            if contains_unverified_claim(answer) or not self._evidence_valid(answer, envelope_payload, cognitive_result.get("epistemic_context", {})):
                self._parse_failure("LLM_UNVERIFIED_CLAIM", prompt, raw)
                return self._unsupported_response(answer, envelope_payload, cognitive_result.get("epistemic_context", {}))
            self._parse_success(prompt, raw); return answer
        except ValueError: return None

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
        prior = self.last_status
        self.last_status = GenerationStatus(True, True, True, True, None, self._estimate_tokens(prompt), len(raw), prior.endpoint, http_status=prior.http_status, generation_budget=prior.generation_budget, raw_output_chars=len(raw), think_marker_found=True, final_output_chars=len(extract_final_answer(raw)[1]), finish_reason=prior.finish_reason, retry_count=prior.retry_count, llm_queue_ms=prior.llm_queue_ms, llm_generation_ms=prior.llm_generation_ms, timeout_stage=prior.timeout_stage)

    def _parse_failure(self, reason: str, prompt: str, raw: str) -> None:
        prior = self.last_status
        self.last_status = GenerationStatus(True, True, True, False, reason, self._estimate_tokens(prompt), len(raw), prior.endpoint, http_status=prior.http_status, generation_budget=prior.generation_budget, raw_output_chars=len(raw), think_marker_found="</think>" in raw, final_output_chars=0, finish_reason=prior.finish_reason, retry_count=prior.retry_count, llm_queue_ms=prior.llm_queue_ms, llm_generation_ms=prior.llm_generation_ms, timeout_stage=prior.timeout_stage)

    @staticmethod
    def _concise_prompt(cognitive_result: dict[str, Any]) -> str:
        return ("[INST] FERMiON has completed cognitive processing. Produce only the final user-facing answer. "
                "Do not discuss internal reasoning or data structures.\nUSER:\n" + str(cognitive_result.get("user_input", ""))[:2200] +
                "\nFERMiON RESULT:\n" + json.dumps(cognitive_result.get("reasoning", {}), default=str)[:1600] + "\n[/INST]")
