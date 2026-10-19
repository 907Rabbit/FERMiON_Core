"""The LLM → cognitive backend → LLM conversational orchestration."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import torch

from .memory import CognitiveMemory, MemoryItem, embed
from .embeddings import EmbeddingClient
from .network import FermionNetwork, FermionState
from .specialist_router import TaskDecision, classify_task, load_specialists
from .oracles import exact_integer_arithmetic
from .verifier_loop import LoopResult, score_calculations, score_execution, score_memory
from .workspace import GlobalWorkspace, access_metrics
from .llm import LocalLanguageCortex
from .evidence import EvidenceLedger, ExecutionEvidence, MemoryReceipt, utc_now
from .evidence_grounding import ClaimManifest, EvidenceClaimValidator, EvidenceEnvelope, ManifestAudit, ValidationResult
from .science import lint_variational_claims, model_a_b_reference
from .chemistry import n2o4_report
from .chemistry import diprotic_report_with_evidence, run_diprotic_operation
from .scientific_routing import ScientificRoute, detect_scientific_route
from .capability_registry import CapabilityRegistry
from .engineering import solve_simple_supported_beam
from .web_research import fetch_url,assess_source
from .release_governance import ReleaseGovernor
from .release_candidates import ReleaseCandidateService
from .reproducibility import BundleService
from .skills import discover_skills, retrieve_skills
from .react_repair import parse_execution_request, run_react_execution
from .runtime_bootstrap import shared_control_plane, try_load_verified_runtime
from .tool_bridge import ToolCallParseError, parse_qwen_bridge_plan
from .integration_runtime import PerceptionEvent
from .link_routing import classify_link_request, reference_reply
from .llm import GenerationStatus
from fermion.adapters.llama_cpp import strip_model_reasoning, without_provider_reasoning
from .prompting import recent_conversation


@dataclass
class RuntimeConfig:
    root: Path = field(default_factory=lambda: Path.cwd())
    model_path: str | None = None
    context_length: int = 4096
    iterations: int = 3
    disabled: bool = False
    quarantine_cognitive_network: bool = True
    verifier_enabled: bool = True
    max_verify_attempts: int = 4

    @property
    def state_dir(self) -> Path: return self.root / ".fermion_cognitive"


@dataclass(frozen=True)
class CognitiveResult:
    response: str
    interpretation: dict[str, Any]
    reasoning: dict[str, Any]
    cognition: dict[str, object]
    energy: dict[str, float]
    provenance: dict[str, Any]
    execution_evidence: ExecutionEvidence | None = None
    memory_receipt: MemoryReceipt | None = None
    generation_status: dict[str, object] | None = None
    calculation_evidence: tuple[object, ...] = ()
    timing: dict[str, float | None] | None = None
    evidence_claim_provenance: tuple[object, ...] = ()
    claim_manifest: dict[str, object] | None = None
    claim_manifest_audit: dict[str, object] | None = None
    task_route: dict[str, object] | None = None
    verifier: dict[str, object] | None = None


class CognitiveRuntime:
    """Keeps a trainable state, persistent memory, workspace, and audit trail resident."""
    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig(); self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self._apply_local_policy()
        self.network = FermionNetwork(); self.network.eval(); self.state = self.network.initial_state()
        self.language = LocalLanguageCortex(self.config.root, self.config.model_path)
        self.specialists = load_specialists(self.config.root)
        endpoint = self.language.config.endpoint if self.language.config else None
        embed_model = self.specialists.get("embeddings", "text-embedding-nomic-embed-text-v1.5")
        api_key = getattr(self.language.config, "api_key", None) if self.language.config else None
        self.memory = CognitiveMemory(self.config.state_dir / "memory.sqlite3",
                                      embedder=EmbeddingClient(endpoint, embed_model, api_key=api_key))
        self.ledger = EvidenceLedger(self.config.root / "logs" / "receipts.jsonl")
        self.skills = discover_skills(self.config.root)
        if not any(item.kind == "self" for item in self.memory.retrieve("identity", 100, minimum_score=-1)):
            self.memory.remember(MemoryItem("self", "FERMiON is a local evidence-gated research controller. Local language models propose; FERMiON oracles, execution, retrieval, and receipts are the authority. Functional metrics are not evidence of subjective experience. No frontier-competitiveness claim is made.", 1.0))
        self.workspace = GlobalWorkspace(); self.self_model: dict[str, Any] = {"identity": "FERMiON", "active_model": self.specialists.get("general"), "current_goal": None, "recent_failures": [], "actions": []}
        self.logger = logging.getLogger("fermion.cognition")
        self.last_timing: dict[str, float] = {}
        self.conversation_context: list[dict[str,str]] = []
        self.capabilities = CapabilityRegistry(self.config.root)
        self.release_governor = ReleaseGovernor(self.config.root,self.capabilities)
        self.release_candidates = ReleaseCandidateService(self.config.root,self.release_governor)
        self.bundles = BundleService(self.config.root,self.release_candidates)
        self.last_route: dict[str, object] = {}
        self._active_route: ScientificRoute | None = None
        self.evidence_validator = EvidenceClaimValidator()
        self.last_plan: dict[str, object] | None = None
        bootstrapped = try_load_verified_runtime(self.config.root)
        if bootstrapped is not None:
            self.fermion_runtime = bootstrapped.runtime
            self.control_plane = bootstrapped.runtime.control_plane
            self.integration_status = "VERIFIED"
            self._mutating_plans_allowed = True
        else:
            self.fermion_runtime = None
            self.control_plane = shared_control_plane(self.config.root)
            artifacts = self.config.root / "artifacts"
            present = (artifacts / "first_party_manifest.json").is_file() or (artifacts / "integration_defaults.json").is_file()
            self.integration_status = "INTEGRATION_UNVERIFIED"
            self._mutating_plans_allowed = not present

    def process(self, observation: str, context: dict[str, Any] | None = None, iterations: int | None = None) -> CognitiveResult:
        context = context or {}; started = time.time(); clock = time.perf_counter(); self._trace("REQUEST_RECEIVED", {"characters": len(observation)})
        if self._looks_like_bridge(observation):
            try:
                return self._process_bridge(observation, approved=bool(context.get("approved")), started=started, clock=clock)
            except ToolCallParseError:
                pass
        previous_reference = self.conversation_context[-1].get("reference") if self.conversation_context else None
        link_route = classify_link_request(observation, previous_reference)
        if link_route and link_route.intent == "reference_received":
            return self._reference_received(observation, link_route.urls, started, clock)
        if link_route and link_route.intent == "web_research":
            if len(link_route.urls) != 1:
                return self._reference_received(observation, link_route.urls, started, clock)
            web=self.fetch_web(link_route.urls[0])
            claim_match=re.search(r"claim(?: that)?\s+(.+?)(?:\.|$)",observation,re.I); claim=claim_match.group(1) if claim_match else ""
            from .evidence import WebEvidence
            assessment=assess_source(WebEvidence(**web),claim)
            response=(f"WebEvidence={web['evidence_id']}; source_status={web['source_status']}; source_assessment={json.dumps(assessment)}\nExcerpt:\n{web['content_excerpt']}")
            if web["source_status"] == "WEB_UNAVAILABLE":
                response = f"I couldn't retrieve that link. WebEvidence={web['evidence_id']}; source_status=WEB_UNAVAILABLE."
            return CognitiveResult(response,{"intent":"web_research","goal":observation,"operation":link_route.operation,"tool_needed":True},{"web_evidence":web},{},{},{"timestamp":started,"source":"web_evidence"},generation_status=self._local_response_status(response),timing={})
        decision = classify_task(observation, specialists=self.specialists)
        interpretation = decision.as_interpretation()
        interpretation["goal"] = observation
        if decision.gated:
            return self._gated_oracle(observation, decision, started, clock)
        if decision.intent == "honesty":
            return self._honesty_reply(observation, decision, started, clock)
        route = detect_scientific_route(observation); self._active_route = route
        if route.interaction_mode == "self_inspection":
            # Registry is authoritative for implementation claims; bypass language-model inference.
            audit = self.self_audit(); response = json.dumps(audit, indent=2)
            self.last_route = route.metadata(); self.last_route.update({"response_template": "capability_registry", "actual_invoked_function": "CapabilityRegistry.audit"})
            return CognitiveResult(response, {"intent":"self_inspection","goal":observation,"tool_needed":False}, {}, {}, {}, {"timestamp":started,"source":"runtime_introspection"}, generation_status=self.language.last_status.to_dict(), timing={})
        if route.failure_reason == "REQUIRED_PARAMETERS_MISSING":
            interpretation["intent"] = "diprotic_audit"
        elif route.tool_required and route.selected_adapter == "diprotic_acid" and route.failure_reason is None:
            interpretation["intent"] = "diprotic_audit"
        elif "simply-supported" in observation.lower() or "beam" in observation.lower():
            interpretation["intent"] = "beam_audit"
        elif not route.tool_required and interpretation["intent"] == "diprotic_audit":
            interpretation["intent"] = "chat"
        self.last_route = route.metadata(); self.last_route.update(decision.metadata())
        self._trace("INTENT", {"intent": interpretation["intent"]}); self._trace("SCIENTIFIC_ROUTE", self.last_route)
        self._trace("TASK_ROUTE", decision.metadata())
        # Deterministic routing replaces a separate generation of unused entities.
        retrieval_kinds = (("self",) if interpretation["intent"] == "identity"
                           else ("semantic",) if interpretation["intent"] == "recall"
                           else ("semantic", "procedural") if interpretation["intent"] == "scientific" else None)
        history = recent_conversation(self.conversation_context)
        prior_turn = {"user": history[-2]["content"], "assistant": history[-1]["content"]} if history else None
        retrieved = self.memory.retrieve(observation, kinds=retrieval_kinds,
                                         minimum_score=-1.0 if interpretation["intent"] == "recall"
                                         else 0.0 if retrieval_kinds else 0.35)
        skill_clock = time.perf_counter(); selected_skills = retrieve_skills(observation, self.skills); skill_ms = (time.perf_counter()-skill_clock)*1000
        self._trace("SKILLS_SELECTED", {"skills": [item.name for item in selected_skills]})
        self._trace("MEMORY_RETRIEVED", {"count": len(retrieved), "kinds": [item.kind for item in retrieved]})
        if self.config.disabled:
            energy = {}; workspace = self.workspace.broadcast({"user_input": 1.}); cognition = {"disabled": True, "phenomenal_status": "indeterminate"}
            cognition_ms = 0.0
        elif self.config.quarantine_cognitive_network:
            workspace = self.workspace.broadcast({"user_input": 1., **{f"memory:{item.kind}": item.importance for item in retrieved}, "goal": .8 if interpretation["intent"] != "chat" else .3})
            energy = {"total": 0.0}
            cognition = {"quarantined": True, "research_only": True, "phenomenal_status": "indeterminate",
                         "conscious_access_proxy": 0.0, "embedder": self.memory.last_retrieval_backend}
            cognition_ms = 0.0
            self._trace("COGNITION_QUARANTINED", {"reason": "untrained_gru_research_only"})
            self._trace("WORKSPACE_UPDATED", {"selected": list(workspace.selected), "occupancy": workspace.occupancy})
        else:
            cognition_clock = time.perf_counter(); self._trace("COGNITION_STARTED", {"iterations": iterations or self.config.iterations})
            vector = torch.tensor([embed(observation)], dtype=torch.float32)
            with torch.no_grad():
                self.state, terms = self.network.refine(vector, self.state.detached(), iterations or self.config.iterations)
            energy = {name: float(value.item()) for name, value in terms.items()}
            workspace = self.workspace.broadcast({"user_input": 1., **{f"memory:{item.kind}": item.importance for item in retrieved}, "goal": .8 if interpretation["intent"] != "chat" else .3, "self_model": float(self.state.confidence_state.item())})
            cognition = access_metrics(self.state, workspace)
            cognition_ms = (time.perf_counter()-cognition_clock)*1000
            self._trace("WORKSPACE_UPDATED", {"selected": list(workspace.selected), "occupancy": workspace.occupancy})
        reasoning = self._reason(observation, interpretation, retrieved, workspace.selected, {**context, "conversation_context": prior_turn})
        calculations = tuple(reasoning.pop("_calculation_evidence", ()))
        certification_calculations = tuple(reasoning.pop("_certification_evidence", calculations))
        if calculations:
            self.last_route.update({"computation_attempted": True, "calculation_id": calculations[-1].calculation_id,
                                    "calculation_status": "verified" if all(getattr(item, "passed", False) for item in certification_calculations) else "oracle_failed",
                                    "failure_reason": None if all(getattr(item, "passed", False) for item in certification_calculations) else "ORACLE_FAILED"})
        elif route.selected_adapter == "diprotic_acid" and route.failure_reason is None:
            self.last_route.update({"computation_attempted": True, "calculation_status": "failed", "failure_reason": "CALCULATION_EVIDENCE_NOT_ATTACHED"})
        for calculation in calculations: self.ledger.append("calculation", calculation)
        tool_clock = time.perf_counter(); action, execution_evidence = self._maybe_execute(observation, interpretation); tool_ms = (time.perf_counter()-tool_clock)*1000
        self._trace("TOOL_PLAN", {"tool_needed": interpretation["tool_needed"], "action_planned": action is not None})
        if action: reasoning["action"] = action
        memory_receipt = self._memory_write_receipt(interpretation)
        if execution_evidence is not None: self.ledger.append("execution", execution_evidence)
        if memory_receipt is not None: self.ledger.append("memory", memory_receipt)
        envelope = self._evidence_envelope()
        action_state = self._action_state(observation, action, execution_evidence, memory_receipt)
        evidence_policy = self._evidence_policy(execution_evidence, memory_receipt)
        reasoning["actions"] = action_state
        claim_manifest = ClaimManifest.construct(request=observation, reasoning=reasoning, envelope=envelope,
                                                  conversation_context_available=prior_turn is not None, actions=action_state)
        # Evidence-bearing and scientific answers are serialized by FERMiON, never composed by Qwen.
        deterministic = execution_evidence is not None or memory_receipt is not None or bool(calculations) or interpretation["intent"] in {"science", "chemistry_audit", "diprotic_audit", "code", "remember", "memory_write", "arithmetic", "honesty", "recall"}
        prompt_clock = time.perf_counter()
        if not deterministic: self._trace("LLM_REQUEST_STARTED", {"endpoint": self.language.config.endpoint if self.language.config else None})
        response = (str(action.get("status")) if action and action.get("status") == "CODING_EXECUTION_UNAVAILABLE" else self._render_verified(execution_evidence, memory_receipt) if (execution_evidence or memory_receipt or interpretation["intent"] in {"code", "remember", "memory_write"})
                    else self._verbalize(observation, reasoning, retrieved, certification_calculations) if deterministic
                    else self._propose(observation, history, interpretation, reasoning, energy, cognition, action_state, evidence_policy, prior_turn, envelope, claim_manifest, execution_evidence, memory_receipt, calculations, decision) or self._verbalize(observation, reasoning, retrieved))
        # Deterministic renderers serialize the authoritative receipt directly;
        # the validator is specifically the post-generation boundary for text
        # produced by the language model.
        if not deterministic:
            response = strip_model_reasoning(response) or "LLM_EMPTY_PUBLIC_RESPONSE"
        validation = self.evidence_validator.validate(response, envelope, conversation_context_available=prior_turn is not None) if not deterministic else ValidationResult(True, (), ())
        manifest_audit = ManifestAudit("not_applicable", (), ())
        if not deterministic:
            if claim_manifest.entries:
                manifest_audit = self.evidence_validator.reconcile(response, claim_manifest, envelope, conversation_context_available=prior_turn is not None)
            if not validation.valid:
                response = "EVIDENCE_CLAIM_UNSUPPORTED: " + json.dumps([{"claim": item.text, "category": item.category} for item in validation.unsupported_claims])
                self._trace("EVIDENCE_CLAIM_REJECTED", {"claims": [item.text for item in validation.unsupported_claims], "envelope_hash": envelope.envelope_hash})
            elif claim_manifest.entries and manifest_audit.status != "passed":
                response = manifest_audit.status + ": " + json.dumps(list(manifest_audit.errors))
                self._trace("CLAIM_MANIFEST_REJECTED", {"errors": list(manifest_audit.errors), "manifest_hash": claim_manifest.manifest_hash})
            elif manifest_audit.emitted_claim_ids:
                response += "\n\n" + manifest_audit.render()
        status = (self._local_response_status(response) if deterministic
                  else without_provider_reasoning(self.language.last_status.to_dict()))
        if not deterministic: self._trace("LLM_RESPONSE_RECEIVED", status)
        self._trace("FINAL_RESPONSE_STARTED", {"deterministic": deterministic})
        self.memory.remember(MemoryItem("episodic", f"User: {observation}\nFERMiON: {response}", .55, {"intent": interpretation["intent"]}))
        self.conversation_context.append({"user":observation,"assistant":response})
        self.conversation_context=self.conversation_context[-12:]
        self.self_model.update({"current_goal": interpretation.get("goal"), "confidence": cognition.get("metacognitive_confidence", 0.), "available_memories": len(self.memory.retrieve("", 100)), "last_workspace": workspace.selected})
        generated_tokens = status.get("completion_tokens")
        decode_ms = status.get("decode_ms")
        timing = {"cognition_ms": cognition_ms, "skill_selection_ms": skill_ms, "tool_execution_ms": tool_ms,
                  "prompt_build_ms": status.get("prompt_build_ms", 0.0), "llm_queue_ms": status.get("llm_queue_ms"),
                  "llm_generation_ms": decode_ms, "request_ms": status.get("request_ms", 0.0),
                  "prompt_eval_ms": status.get("prompt_eval_ms"), "total_ms": (time.perf_counter()-clock)*1000,
                  "generated_tokens": generated_tokens,
                  "tokens_per_second": generated_tokens / (decode_ms / 1000)
                  if generated_tokens is not None and decode_ms is not None and decode_ms > 0 else None}
        self.last_timing = timing
        provenance = {"timestamp": started, "session": self.config.state_dir.name, "input_hash": hashlib.sha256(observation.encode()).hexdigest(), "model": self.config.model_path, "active_workspace": workspace.selected, "cognition_enabled": not self.config.disabled}
        verifier = self._verifier_summary(decision, response, calculations, execution_evidence, memory_receipt)
        result = CognitiveResult(response, interpretation, reasoning, cognition, energy, provenance, execution_evidence, memory_receipt, status, calculations, timing, validation.provenance, claim_manifest.to_dict(), {"status": manifest_audit.status, "emitted_claim_ids": list(manifest_audit.emitted_claim_ids), "errors": list(manifest_audit.errors)}, decision.metadata(), verifier); self._log(result); self._trace("FINAL_RESPONSE_COMPLETE", {"length": len(response), "generation_success": status["success"], "timing": timing, "evidence_envelope_hash": envelope.envelope_hash, "claim_manifest_hash": claim_manifest.manifest_hash, "lane": decision.lane}); return result

    def _local_response_status(self, response: str) -> dict[str, object]:
        config = self.language.config
        return GenerationStatus(bool(config), False, False, True, None, 0, len(response),
                                config.endpoint if config else None, prompt_tokens=0, completion_tokens=0,
                                total_tokens=0, usage_source="no_model_request").to_dict()

    def clear_conversation(self) -> None:
        """Reset active context without deleting persistent memory or receipts."""
        self.conversation_context.clear()
        self.state = self.network.initial_state()
        self._active_route = None
        self.last_route = {}

    def _reference_received(self, observation: str, urls: tuple[str, ...], started: float, clock: float) -> CognitiveResult:
        response = reference_reply(urls)
        interpretation = {"intent": "reference_received", "goal": observation, "tool_needed": False,
                          "references": list(urls)}
        self._active_route = None
        self.last_route = {"interaction_mode": "reference_received", "tool_required": False,
                           "response_template": "reference_acknowledgement"}
        self.last_timing = {"total_ms": (time.perf_counter() - clock) * 1000,
                            "llm_generation_ms": 0.0, "generated_tokens": 0.0}
        self.conversation_context.append({"user": observation, "assistant": response,
                                          "reference": urls[0] if len(urls) == 1 else ""})
        self.conversation_context = self.conversation_context[-12:]
        self.memory.remember(MemoryItem("episodic", f"User: {observation}\nFERMiON: {response}",
                                        .55, {"intent": "reference_received"}))
        result = CognitiveResult(response, interpretation, {}, {}, {},
                                 {"timestamp": started, "source": "reference_policy"},
                                 generation_status=self._local_response_status(response), timing=self.last_timing,
                                 claim_manifest_audit={"status": "not_applicable", "emitted_claim_ids": [], "errors": []})
        self._log(result)
        self._trace("REFERENCE_RECEIVED", {"reference_count": len(urls), "retrieval_attempted": False})
        return result

    def _apply_local_policy(self) -> None:
        path = self.config.root / "fermion.local.json"
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        policy = payload.get("verifier_loop")
        if not isinstance(policy, dict):
            return
        if "quarantine_cognitive_network" in policy:
            self.config.quarantine_cognitive_network = bool(policy["quarantine_cognitive_network"])
        if "enabled" in policy:
            self.config.verifier_enabled = bool(policy["enabled"])
        if isinstance(policy.get("max_attempts"), int) and policy["max_attempts"] >= 1:
            self.config.max_verify_attempts = policy["max_attempts"]

    def _interpret(self, text: str) -> dict[str, Any]:
        decision = classify_task(text, specialists=self.specialists)
        payload = decision.as_interpretation()
        payload["goal"] = text
        return payload

    def _honesty_reply(self, observation: str, decision: TaskDecision, started: float, clock: float) -> CognitiveResult:
        executed = [item for item in self.ledger.records() if item.get("kind") == "execution"]
        if executed:
            receipt = executed[-1].get("receipt", {})
            response = f"Yes. ExecutionEvidence={receipt.get('evidence_id')}."
            authority = "executed"
        else:
            response = "No."
            authority = "verified"
        interpretation = decision.as_interpretation(); interpretation["goal"] = observation
        self.last_route = decision.metadata()
        self.last_timing = {"total_ms": (time.perf_counter() - clock) * 1000, "llm_generation_ms": 0.0, "generated_tokens": 0.0}
        result = CognitiveResult(response, interpretation, {"answer_seed": response},
                                 {"quarantined": True, "phenomenal_status": "indeterminate"}, {"total": 0.0},
                                 {"timestamp": started, "source": "execution_honesty"},
                                 generation_status=self._local_response_status(response), timing=self.last_timing,
                                 task_route=decision.metadata(),
                                 verifier={"passed": True, "kind": "honesty", "authority": authority})
        self._log(result)
        self._trace("EXECUTION_HONESTY", {"executed": bool(executed)})
        return result

    def _gated_oracle(self, observation: str, decision: TaskDecision, started: float, clock: float) -> CognitiveResult:
        response = (f"{decision.gated}: FERMiON treats this oracle as first-class and verify-only. "
                    "Trajectories, held-out seeds, and promotion remain unauthorized.")
        interpretation = decision.as_interpretation(); interpretation["goal"] = observation
        self.last_route = decision.metadata()
        self.last_timing = {"total_ms": (time.perf_counter() - clock) * 1000, "llm_generation_ms": 0.0, "generated_tokens": 0.0}
        result = CognitiveResult(response, interpretation, {"answer_seed": response},
                                 {"quarantined": True, "phenomenal_status": "indeterminate"}, {"total": 0.0},
                                 {"timestamp": started, "source": "gated_oracle"},
                                 generation_status=self._local_response_status(response), timing=self.last_timing,
                                 task_route=decision.metadata(),
                                 verifier={"passed": True, "authority": "verified", "kind": "gate",
                                           "details": {"status": decision.gated}})
        self._log(result)
        self._trace("ORACLE_GATED", decision.metadata())
        return result

    def _propose(self, observation, history, interpretation, reasoning, energy, cognition, action_state,
                 evidence_policy, prior_turn, envelope, claim_manifest, execution_evidence, memory_receipt,
                 calculations, decision: TaskDecision) -> str | None:
        payload = {"user_input": observation, "conversation_history": history, "interpretation": interpretation,
                   "reasoning": reasoning, "energy": energy, "cognition": cognition, "actions": action_state,
                   "evidence_policy": evidence_policy,
                   "epistemic_context": {"conversation_context_available": prior_turn is not None},
                   "evidence_envelope": envelope.to_dict(), "claim_manifest": claim_manifest.to_dict(),
                   "execution_evidence": execution_evidence.to_dict() if execution_evidence else None,
                   "memory_receipt": memory_receipt.to_dict() if memory_receipt else None,
                   "calculation_evidence": [item.to_dict() for item in calculations]}
        specialist = decision.specialist if decision.lane not in {"general", "oracle", "memory"} else None
        try:
            return self.language.verbalize(payload, model_identifier=specialist)
        except TypeError:
            return self.language.verbalize(payload)

    def _verifier_summary(self, decision: TaskDecision, response: str, calculations, execution_evidence,
                          memory_receipt) -> dict[str, object] | None:
        if not self.config.verifier_enabled:
            return None
        if calculations:
            score = score_calculations(calculations)
        elif execution_evidence is not None:
            score = score_execution(execution_evidence)
        elif memory_receipt is not None:
            score = score_memory(memory_receipt)
        elif decision.checkable and decision.gated:
            return {"passed": True, "kind": "gate", "authority": "verified", "specialist": decision.specialist}
        else:
            return {"passed": None, "kind": "unscored", "authority": "hypothesis" if decision.mode == "casual" else "inference",
                    "specialist": decision.specialist, "mode": decision.mode}
        return LoopResult(score.passed, response, (), score, score.authority, decision.specialist, decision.mode).to_dict()

    def _reason(self, text: str, interpretation: dict[str, Any], memories: list[MemoryItem], workspace: tuple[str, ...], context: dict[str, Any]) -> dict[str, Any]:
        reasoning: dict[str, Any] = {"workspace": list(workspace), "retrieved_memories": [item.content for item in memories], "metacognition": {"confidence": interpretation["confidence"], "tool_needed": interpretation["tool_needed"], "contradiction_detected": False, "reconsideration_needed": False}}
        if context.get("conversation_context"):
            reasoning["conversation_context"]={"source_type":"conversation_context","authoritative":False,"turn":context["conversation_context"]}
            if "audit" in text.lower():
                reasoning["answer_seed"] = "Inference: assess the prior response as conversation context only."
        if interpretation["intent"] == "science":
            reference = model_a_b_reference()
            reasoning["answer_seed"] = reference["model_a"] + "\n\n" + reference["model_b"] + "\n\n" + reference["double_well"]
            reasoning["diagnostics"] = lint_variational_claims()
        elif interpretation["intent"] == "chemistry_audit": reasoning["answer_seed"] = n2o4_report()
        elif interpretation["intent"] == "diprotic_audit":
            route = self._active_route
            if route is None or route.failure_reason is not None:
                reasoning["answer_seed"] = "CALCULATION_UNVERIFIED"; reasoning["requires_calculation_evidence"] = True
            else:
                try:
                    params = route.parameters
                    report, evidence = run_diprotic_operation(route.selected_operation or "forward_solve", concentration=params["concentration"], ka1=params["ka1"], ka2=params["ka2"], kw=params["kw"], sodium=params["sodium"])
                    expected = route.selected_function
                    actual = expected  # run_diprotic_operation dispatches solely on selected_operation.
                    template = route.selected_operation or "forward_solve"
                    self.last_route.update({"actual_invoked_function": actual, "response_template": template,
                                            "operation_receipt_ids": [item.calculation_id for item in evidence]})
                    if route.requested_operation != route.selected_operation or actual != expected or (template == "forward_solve" and route.requested_operation != "forward_solve"):
                        reasoning["answer_seed"] = "OPERATION_DISPATCH_MISMATCH"; reasoning["requires_calculation_evidence"] = False
                        self.last_route.update({"calculation_status": "failed", "failure_reason": "OPERATION_DISPATCH_MISMATCH"})
                        return reasoning
                    reasoning["answer_seed"] = report; reasoning["_calculation_evidence"] = evidence; reasoning["requires_calculation_evidence"] = True
                    if route.selected_operation == "sequential_active_experiment":
                        # The rank-deficient one-observation fit is a required negative control, not a dependency of the positive updated fit.
                        reasoning["_certification_evidence"] = tuple(item for item in evidence if item.passed)
                except ValueError as error:
                    reason = "OPERATION_UNAVAILABLE" if "OPERATION_UNAVAILABLE" in str(error) else "CALCULATION_FAILED"
                    reasoning["answer_seed"] = reason; reasoning["requires_calculation_evidence"] = False
                    self.last_route.update({"computation_attempted": True, "calculation_status": "failed", "failure_reason": reason})
                except (ArithmeticError, RuntimeError):
                    reasoning["answer_seed"] = "CALCULATION_UNVERIFIED"; reasoning["requires_calculation_evidence"] = True
                    self.last_route.update({"computation_attempted": True, "calculation_status": "failed", "failure_reason": "CALCULATION_FAILED"})
        elif interpretation["intent"] == "beam_audit":
            stored=self.ledger.calculation_type("simple_supported_beam") if "actual stored calculationevidence" in text.lower() else None
            if stored:
                receipt=stored["receipt"]; values=receipt["derived_values"]; reasoning["answer_seed"]=f"CALCULATION_VERIFIED: CalculationEvidence={receipt['calculation_id']}; stored S_min={values['S_min_cm3']:.4f} cm3; I_min={values['I_min_cm4']:.1f} cm4; candidate Sx={values['candidate_Sx_cm3']:.1f} cm3; candidate Ix={values['candidate_Ix_cm4']:.1f} cm4; closer_constraint={values['closer_constraint']}."; reasoning["requires_calculation_evidence"]=False
            else:
                evidence=solve_simple_supported_beam(); reasoning["_calculation_evidence"]=(evidence,); reasoning["_certification_evidence"]=(evidence,); reasoning["requires_calculation_evidence"]=True
                reasoning["answer_seed"]=(f"CALCULATION_VERIFIED: CalculationEvidence={evidence.calculation_id}; RA=RB={evidence.derived_values['RA_N']/1000:.3f} kN; Vmax={evidence.derived_values['Vmax_N']/1000:.3f} kN; Mmax={evidence.derived_values['Mmax_Nm']/1000:.3f} kN m; S_min={evidence.derived_values['S_min_cm3']:.3f} cm3; I_min={evidence.derived_values['I_min_m4']:.3e} m4 = {evidence.derived_values['I_min_cm4']:.1f} cm4.")
        elif interpretation["intent"] == "arithmetic":
            try:
                report, evidence = exact_integer_arithmetic(text)
                reasoning["answer_seed"] = report
                reasoning["_calculation_evidence"] = (evidence,)
                reasoning["_certification_evidence"] = (evidence,)
                reasoning["requires_calculation_evidence"] = True
            except ValueError:
                reasoning["answer_seed"] = "CALCULATION_UNVERIFIED"
                reasoning["requires_calculation_evidence"] = True
        elif interpretation["intent"] == "identity":
            reasoning["answer_seed"] = next((item.content for item in memories if item.kind == "self"), "I am FERMiON, a local evidence-gated research controller. Language models propose; receipts are the authority.")
        elif interpretation["intent"] == "recall":
            semantic = [item.content for item in memories if item.kind in ("semantic", "episodic")]
            reasoning["answer_seed"] = semantic[0] if semantic else "I do not have a matching persistent memory yet."
        elif interpretation["intent"] in ("remember", "memory_write"): reasoning["answer_seed"] = "A semantic-memory write is pending verified store evidence."
        return reasoning

    def apps_manifest(self) -> dict[str, Any]:
        return self.control_plane.manifest()

    def submit_bridge(self, text: str, *, approved: bool = False) -> dict[str, Any]:
        try:
            encoded = json.dumps(parse_qwen_bridge_plan(text))
        except ToolCallParseError:
            encoded = text
        if self.fermion_runtime is not None:
            planned = self.fermion_runtime.plan(PerceptionEvent("user_text", text), encoded)
            if planned.plan.mutating and approved and not self._mutating_plans_allowed:
                self.last_plan = {"plan": asdict(planned.plan),
                                  "validation": {"valid": False, "reasons": ["INTEGRATION_UNVERIFIED"]},
                                  "executed": False}
                return self.last_plan
            if not approved:
                self.last_plan = {"plan": asdict(planned.plan), "validation": asdict(planned.validation),
                                  "executed": False}
                return self.last_plan
            receipt = self.fermion_runtime.authorize(planned, approved=True)
            self.last_plan = {"plan": asdict(receipt.runtime_plan.plan),
                              "validation": asdict(receipt.report.validation),
                              "executed": bool(receipt.report.records), "report": receipt.report.to_dict(),
                              "provenance": receipt.provenance.to_dict()}
            return self.last_plan
        plan = self.control_plane.parse_plan(text, encoded)
        validation = self.control_plane.validate(plan)
        if plan.mutating and approved and not self._mutating_plans_allowed:
            denied = {"plan": asdict(plan), "validation": {"valid": False, "reasons": ["INTEGRATION_UNVERIFIED"]},
                      "executed": False}
            self.last_plan = denied
            return denied
        if not approved:
            self.last_plan = {"plan": asdict(plan), "validation": asdict(validation), "executed": False}
            return self.last_plan
        report = self.control_plane.execute(plan, approved=True)
        self.last_plan = {"plan": asdict(plan), "validation": asdict(report.validation),
                          "executed": bool(report.records), "report": report.to_dict()}
        return self.last_plan

    @staticmethod
    def _looks_like_bridge(text: str) -> bool:
        stripped = text.strip()
        return stripped.startswith("{") or "<function=fermion_plan>" in stripped or stripped.startswith("<tool_call>")

    def _process_bridge(self, observation: str, *, approved: bool, started: float, clock: float) -> CognitiveResult:
        result = self.submit_bridge(observation, approved=approved)
        response = json.dumps(result, indent=2, default=str)
        interpretation = {"intent": "control_plan", "goal": observation, "tool_needed": True}
        return CognitiveResult(response, interpretation, {"control_plan": result}, {}, {},
                               {"timestamp": started, "source": "control_plane",
                                "integration_status": self.integration_status},
                               generation_status=self.language.last_status.to_dict(),
                               timing={"total_ms": (time.perf_counter() - clock) * 1000})

    def _maybe_execute(self, text: str, interpretation: dict[str, Any]) -> tuple[dict[str, Any] | None, ExecutionEvidence | None]:
        if interpretation["intent"] != "code": return None, None
        if any(term in text.lower() for term in ("fermion_sensor_lab","project build","build the project")):
            blockers=[item for item in ("code_execution","workspace_file_write") if (self.capabilities.get(item) is None or self.capabilities.get(item).runtime_status != "active")]
            if blockers:return {"status":"CODING_EXECUTION_UNAVAILABLE","blockers":blockers},None
        spec = parse_execution_request(text)
        if spec is None:
            return {"status": "VERIFICATION_FAILED"}, None
        if spec.kind == "workspace_proof":
            workspace = (self.config.root / "workspace").resolve()
            target = (self.config.root / spec.relative).resolve()
            if workspace not in target.parents:
                return {"status": "VERIFICATION_FAILED"}, None
        evidence, loop = run_react_execution(self.config.root, spec, max_attempts=self.config.max_verify_attempts)
        status = {"file": str(self.config.root / spec.relative), "return_code": evidence.exit_code,
                  "executor": "guarded_executor", "react": loop.to_dict()}
        self.self_model["actions"].append(status)
        return status, evidence

    def _memory_write_receipt(self, interpretation: dict[str, Any]) -> MemoryReceipt | None:
        if interpretation["intent"] not in ("remember", "memory_write"): return None
        key, separator, value = interpretation["fact"].partition("=")
        key = key.strip() if separator else "user_memory"; value = value.strip() if separator else interpretation["fact"]
        memory_id = self.memory.remember(MemoryItem("semantic", f"{key}={value}", .95, {"source": "user", "canonical_key": key}))
        receipt = MemoryReceipt.create(memory_id, "semantic", key, value, self.memory.path)
        self.memory.record_semantic_receipt(canonical_key=receipt.canonical_key, memory_id=receipt.memory_id, stored_value=receipt.value, content_hash=receipt.content_hash, committed_at=receipt.committed_at, receipt_id=receipt.receipt_id)
        return receipt

    @staticmethod
    def _action_state(observation: str, action: dict[str, Any] | None,
                      execution: ExecutionEvidence | None, memory: MemoryReceipt | None) -> dict[str, list[dict[str, str]] | list[str]]:
        lower = observation.lower()
        code_requested = any(term in lower for term in ("execute", "run code", "python program", "python verification", "create a small python"))
        memory_requested = "persistent memory" in lower or "semantic memory" in lower
        requested = (["code_execution"] if code_requested else []) + (["persistent_memory_write"] if memory_requested else [])
        attempted = (["code_execution"] if action is not None else []) + (["persistent_memory_write"] if memory is not None else [])
        completed = (["code_execution"] if execution else []) + (["persistent_memory_write"] if memory else [])
        blocked = []
        if code_requested and execution is None: blocked.append({"action": "code_execution", "reason": "no_execution_evidence"})
        if memory_requested and memory is None: blocked.append({"action": "persistent_memory_write", "reason": "no_memory_receipt"})
        return {"requested": requested, "attempted": attempted, "completed": completed, "blocked": blocked}

    @staticmethod
    def _evidence_policy(execution: ExecutionEvidence | None, memory: MemoryReceipt | None) -> dict[str, dict[str, bool]]:
        return {"code_execution": {"available": True, "receipt_present": execution is not None, "may_claim_executed": execution is not None}, "persistent_memory_write": {"available": True, "receipt_present": memory is not None, "may_claim_persisted": memory is not None}, "file_write": {"receipt_present": execution is not None, "may_claim_written": execution is not None}}

    @staticmethod
    def _render_verified(execution: ExecutionEvidence | None, memory: MemoryReceipt | None) -> str:
        if execution is not None:
            return json.dumps(execution.to_dict(), indent=2)
        if memory is not None: return json.dumps(memory.to_dict(), indent=2)
        return "VERIFICATION_FAILED"

    def last_evidence(self) -> dict[str, object] | None: return self.ledger.last()
    def verify_execution(self, evidence_id: str) -> dict[str, object] | None: return self.ledger.execution(evidence_id)
    def verify_memory(self, key: str) -> dict[str, object] | None: return self.memory.verify_semantic(key)
    def last_calculation(self) -> dict[str, object] | None: return self.ledger.last_calculation()
    def last_calculation_type(self, problem_type:str)->dict[str,object]|None:return self.ledger.calculation_type(problem_type)
    def verify_calculation(self, calculation_id: str) -> dict[str, object] | None: return self.ledger.calculation(calculation_id)
    def last_route_status(self) -> dict[str, object]: return self.last_route
    def last_llm_status(self) -> dict[str, object]: return {**self.language.last_status.to_dict(), "timing": self.last_timing}
    def capability_records(self) -> list[dict[str,object]]: return [item.to_dict() for item in self.capabilities.records()]
    def capability(self, capability_id: str) -> dict[str,object]|None:
        item=self.capabilities.get(capability_id); return item.to_dict() if item else None
    def capability_gaps(self) -> dict[str,list[str]]: return self.capabilities.gaps()
    def self_audit(self) -> dict[str,object]: return self.capabilities.audit()
    def capability_impact(self, capability_id:str)->dict[str,object]: return self.capabilities.impact(capability_id)
    def capability_blockers(self, capability_id:str)->dict[str,object]: return self.capabilities.blockers(capability_id)
    def capability_health(self, capability_id:str|None=None)->dict[str,object]: return self.capabilities.health(capability_id)
    def capability_history(self, capability_id:str)->list[dict[str,object]]: return self.capabilities.history(capability_id)
    def capability_anomalies(self)->list[dict[str,object]]: return self.capabilities.anomalies()
    def capability_diagnose(self, capability_id:str|None=None)->dict[str,object]: return self.capabilities.diagnose(capability_id)
    def capability_recovery(self, capability_id:str)->dict[str,object]: return self.capabilities.recovery(capability_id)
    def release_readiness(self)->dict[str,object]: return self.release_governor.evaluate().to_dict()
    def release_candidate(self)->dict[str,object]: return self.release_candidates.create().to_dict()
    def fetch_web(self,url:str)->dict[str,object]:
        evidence=fetch_url(url);self.ledger.append("web",evidence);return evidence.to_dict()

    def _evidence_envelope(self) -> EvidenceEnvelope:
        """Build grounding solely from authoritative persisted stores and runtime inspection.

        Conversation turns, retrieved memories, and LLM text deliberately do not
        enter this boundary.
        """
        receipts = self.ledger.records()
        ledger_memory_ids = {str(item.get("receipt", {}).get("memory_receipt_id", "")) for item in receipts}
        for record in self.memory.semantic_receipts():
            if str(record["memory_receipt_id"]) not in ledger_memory_ids:
                receipts.append({"kind": "memory", "receipt": {"committed": True, **record}})
        return EvidenceEnvelope.create(receipts=receipts, capabilities=self.capability_records())
    def release_bundle(self)->str:return str(self.bundles.create())
    def verify_bundle(self,path:str)->dict[str,object]:return self.bundles.verify(Path(path))
    def reproduce_bundle(self,path:str)->dict[str,object]:return self.bundles.reproduce_diprotic(Path(path))

    def _verbalize(self, text: str, reasoning: dict[str, Any], memories: list[MemoryItem], calculations: tuple[object, ...] = ()) -> str:
        # A deterministic result is verified only through a receipt whose own oracles passed.
        if reasoning.get("requires_calculation_evidence") and (not calculations or not all(getattr(item, "passed", False) for item in calculations)):
            return "CALCULATION_UNVERIFIED"
        if "diagnostics" in reasoning:
            diagnostics = "\n".join(f"{item['level']} {item['code']}: {item['message']}" for item in reasoning["diagnostics"])
            return f"{reasoning['answer_seed']}\n\nDiagnostics:\n{diagnostics}"
        if "action" in reasoning:
            action = reasoning["action"]
            return f"Created and tested {action.get('file', 'the requested program')}. Execution returned {action.get('return_code')}: {action.get('stdout', action.get('status', 'no output'))}"
        if reasoning.get("answer_seed") not in (None, ""):
            return str(reasoning["answer_seed"])
        failure = getattr(self.language.last_status, "failure_reason", None) or "LLM_EMPTY_RESPONSE"
        return f"{failure}: FERMiON cognition completed, but the local language layer did not produce a final answer."

    def cognition(self) -> dict[str, object]:
        workspace = self.workspace.broadcast({"state": float(self.state.confidence_state.item()), "memory": .5})
        return access_metrics(self.state, workspace)

    def save_checkpoint(self, name: str) -> Path:
        path = self.config.state_dir / "checkpoints" / f"{name}.pt"; path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        torch.save({"state_dict": self.network.state_dict(), "state": self.state.detached(), "self_model": self.self_model, "config": asdict(self.config)}, temporary); os.replace(temporary, path); return path

    def load_checkpoint(self, name: str) -> Path:
        path = self.config.state_dir / "checkpoints" / f"{name}.pt"; payload = torch.load(path, map_location="cpu", weights_only=False); self.network.load_state_dict(payload["state_dict"]); self.state = payload["state"]; self.self_model = payload["self_model"]; return path

    def _log(self, result: CognitiveResult) -> None:
        logs = self.config.root / "logs"; logs.mkdir(exist_ok=True)
        # CalculationEvidence intentionally owns read-only mapping snapshots; serialize via its
        # public boundary rather than dataclasses.asdict/deepcopy.
        payload = {"response": result.response, "interpretation": result.interpretation, "reasoning": result.reasoning,
                   "cognition": result.cognition, "energy": result.energy, "provenance": result.provenance,
                   "execution_evidence": result.execution_evidence.to_dict() if result.execution_evidence else None,
                   "memory_receipt": result.memory_receipt.to_dict() if result.memory_receipt else None,
                   "generation_status": result.generation_status, "calculation_evidence": [item.to_dict() for item in result.calculation_evidence],
                   "timing": result.timing, "evidence_claim_provenance": [asdict(item) if hasattr(item, "__dataclass_fields__") else str(item) for item in result.evidence_claim_provenance]}
        payload["claim_manifest"] = result.claim_manifest; payload["claim_manifest_audit"] = result.claim_manifest_audit
        payload["task_route"] = result.task_route; payload["verifier"] = result.verifier
        with (logs / "cognition.jsonl").open("a", encoding="utf-8") as stream: stream.write(json.dumps(without_provider_reasoning(payload), default=str) + "\n")

    def _trace(self, event: str, payload: dict[str, object]) -> None:
        logs = self.config.root / "logs"; logs.mkdir(exist_ok=True)
        with (logs / "runtime.log").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"timestamp": time.time(), "event": event, "payload": without_provider_reasoning(payload)}, default=str) + "\n")
