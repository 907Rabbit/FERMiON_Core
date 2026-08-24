"""Read-only evidence grounding for final language synthesis.

This boundary is deliberately independent from conversation memory and LLM output.
Only receipts and runtime inspection records can enter an :class:`EvidenceEnvelope`.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .evidence import canonical_json


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Immutable, authoritative grounding passed to a language model as read-only data."""
    receipts: tuple[Mapping[str, Any], ...]
    capabilities: tuple[Mapping[str, Any], ...]
    envelope_hash: str

    @classmethod
    def create(cls, *, receipts: Iterable[dict[str, Any]], capabilities: Iterable[dict[str, Any]]) -> "EvidenceEnvelope":
        frozen_receipts = tuple(_freeze(item) for item in receipts)
        frozen_capabilities = tuple(_freeze(item) for item in capabilities)
        payload = {"receipts": _plain(frozen_receipts), "capabilities": _plain(frozen_capabilities)}
        import hashlib
        return cls(frozen_receipts, frozen_capabilities, hashlib.sha256(canonical_json(payload).encode()).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "fermion.evidence-envelope.v1", "receipts": _plain(self.receipts),
                "capabilities": _plain(self.capabilities), "envelope_hash": self.envelope_hash,
                "authoritative_sources": ["execution_ledger", "calculation_ledger", "web_ledger",
                                          "memory_receipt_store", "runtime_capability_registry"]}

    def receipt_ids(self) -> set[str]:
        result: set[str] = set()
        for entry in self.receipts:
            receipt = entry.get("receipt", entry)
            for field in ("evidence_id", "calculation_id", "memory_receipt_id", "receipt_id"):
                value = receipt.get(field)
                if isinstance(value, str): result.add(value)
        return result

    def values(self, field: str) -> set[str]:
        found: set[str] = set()
        def walk(value: Any) -> None:
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if key == field and isinstance(item, (str, int)):
                        found.add(str(item))
                    walk(item)
            elif isinstance(value, tuple):
                for item in value: walk(item)
        for entry in self.receipts: walk(entry)
        return found

    def successful_execution_ids(self) -> set[str]:
        result = set()
        for entry in self.receipts:
            receipt = entry.get("receipt", {})
            if entry.get("kind") == "execution" and receipt.get("exit_code") == 0:
                result.add(str(receipt.get("evidence_id")))
        return result

    def certified_calculation_ids(self) -> set[str]:
        result = set()
        for entry in self.receipts:
            receipt = entry.get("receipt", {})
            if entry.get("kind") == "calculation" and receipt.get("certification_status") == "verified":
                result.add(str(receipt.get("calculation_id")))
        return result

    def capability(self, capability_id: str) -> Mapping[str, Any] | None:
        return next((item for item in self.capabilities if item.get("capability_id") == capability_id), None)


@dataclass(frozen=True)
class EvidenceClaim:
    text: str
    category: str
    supported_by: tuple[str, ...] = ()
    authority_required: tuple[str, ...] = ()
    support_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    unsupported_claims: tuple[EvidenceClaim, ...]
    provenance: tuple[EvidenceClaim, ...]


@dataclass(frozen=True)
class ClaimManifestEntry:
    claim_id: str
    normalized_claim: str
    claim_type: str
    required_authority: tuple[str, ...]
    supporting_receipt_ids: tuple[str, ...]
    supporting_fields: tuple[str, ...]
    validation_status: str
    user_visible_label_required: bool = False

    def to_dict(self) -> dict[str, object]:
        return {"claim_id": self.claim_id, "normalized_claim": self.normalized_claim,
                "claim_type": self.claim_type, "required_authority": list(self.required_authority),
                "supporting_receipt_ids": list(self.supporting_receipt_ids),
                "supporting_fields": list(self.supporting_fields), "validation_status": self.validation_status,
                "user_visible_label_required": self.user_visible_label_required}


@dataclass(frozen=True)
class ClaimManifest:
    entries: tuple[ClaimManifestEntry, ...]
    manifest_hash: str

    @classmethod
    def construct(cls, *, request: str, reasoning: Mapping[str, Any], envelope: EvidenceEnvelope,
                  conversation_context_available: bool, actions: Mapping[str, Any]) -> "ClaimManifest":
        """Pre-authorize only claim authorities relevant to this turn.

        This is constructed *before* language generation from cognition, the user
        request, and authoritative stores—not from previous LLM prose.
        """
        lower = request.lower(); seed = str(reasoning.get("answer_seed", "")).lower()
        combined = lower + "\n" + seed
        entries: list[ClaimManifestEntry] = []
        number = 0
        def add(text: str, kind: str, authority: tuple[str, ...], ids: Iterable[str], fields: tuple[str, ...], status: str = "validated", label: bool = False) -> None:
            nonlocal number
            number += 1
            entries.append(ClaimManifestEntry(f"claim_{number:04d}", text, kind, authority, tuple(sorted(set(ids))), fields, status, label))

        requested_execution = any(word in combined for word in ("execution", "execute", "run", "program", "code", "test", "evidence"))
        requested_calculation = any(word in combined for word in ("calculation", "calculate", "solve", "beam", "equilibrium", "evidence"))
        requested_web = any(word in combined for word in ("source", "website", "web", "verify this", "citation"))
        requested_memory = "memory" in combined
        requested_capability = any(word in combined for word in ("capability", "available", "can you", "registry"))
        for entry in envelope.receipts:
            receipt = entry.get("receipt", {})
            kind = entry.get("kind")
            if kind == "execution" and requested_execution:
                add("execution receipt-backed claim", "execution_claim", ("ExecutionEvidence",), [str(receipt.get("evidence_id"))], ("exact_command", "exit_code", "artifact_hashes"))
            elif kind == "calculation" and requested_calculation and receipt.get("certification_status") == "verified":
                add("calculation receipt-backed claim", "derived_scientific_claim", ("CalculationEvidence",), [str(receipt.get("calculation_id"))], ("derived_values", "residuals", "passed_oracles", "certification_status"))
            elif kind == "web" and requested_web:
                add("web source-backed claim", "external_source_claim", ("WebEvidence",), [str(receipt.get("evidence_id"))], ("url", "content_sha256", "content_excerpt"))
            elif kind == "memory" and requested_memory:
                add("memory receipt-backed claim", "memory_claim", ("MemoryReceipt",), [str(receipt.get("memory_receipt_id"))], ("canonical_key", "content_hash", "stored_value"))
        if conversation_context_available:
            add("prior response is available as conversation context", "conversation_claim", ("conversation_context",), ("conversation_context:prior_turn",), ("prior_turn",))
        if requested_capability:
            for capability in envelope.capabilities:
                add(f"runtime capability {capability.get('capability_id')}", "runtime_capability_claim", ("runtime_capability_registry",), (str(capability.get("capability_id")),), ("runtime_status", "implementation_status"))
        for blocked in actions.get("blocked", []) if isinstance(actions, Mapping) else []:
            action = str(blocked.get("action", "unknown"))
            add(f"{action} unavailable for this claim", "unavailable_claim", ("action_state",), (), ("blocked",), "unavailable")
        # A cognition-produced inferential seed is allowed only if it becomes
        # visibly labeled in the final answer.
        if EvidenceClaimValidator.INFERENCE_RE.search(str(reasoning.get("answer_seed", ""))):
            add("cognition interpretive inference", "interpretive_inference", ("LLM_inference",), (), (), "allowed", True)
        canonical = [entry.to_dict() for entry in entries]
        import hashlib
        return cls(tuple(entries), hashlib.sha256(canonical_json(canonical).encode()).hexdigest())

    def to_dict(self) -> dict[str, object]:
        return {"schema": "fermion.claim-manifest.v1", "manifest_hash": self.manifest_hash,
                "claims": [entry.to_dict() for entry in self.entries]}


@dataclass(frozen=True)
class ManifestAudit:
    status: str
    emitted_claim_ids: tuple[str, ...]
    errors: tuple[str, ...]

    def render(self) -> str:
        return "ClaimManifest audit: " + canonical_json({"status": self.status, "emitted_claim_ids": list(self.emitted_claim_ids), "errors": list(self.errors)})


class EvidenceClaimValidator:
    """Conservative validator for receipt-like or action/verification claims.

    It intentionally does not evaluate ordinary conceptual prose.  It only guards
    language that asserts an external action, certified result, identifier, hash,
    path, exit code, or live capability state.
    """
    ID_RE = re.compile(r"\b(?:exec|calc|web|memr)_[A-Za-z0-9_-]+\b")
    SHA_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
    PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/][^\s'\"`]+|(?:workspace|logs)[\\/][^\s'\"`]+)")
    EXIT_RE = re.compile(r"\b(?:exit[ _-]?code|return[ _-]?code)\s*(?:is|=|:)?\s*(-?\d+)\b", re.I)
    EXEC_RE = re.compile(r"\b(?:program|script|code|test(?:s)?|command|python)\b[^.\n]{0,70}\b(?:ran|run|executed|completed|passed|succeeded|created|wrote)\b|\b(?:we|i|fermion)\b[^.\n]{0,70}\b(?:executed|ran|wrote|created)\b|\b(?:ran|executed)\s+(?:successfully|without errors?)\b|\ball tests? passed\b", re.I)
    CERT_RE = re.compile(r"\b(?:CALCULATION_)?VERIFIED\b|\bCERTIFIED\b|\b(?:all\s+)?(?:oracles?|checks?)\s+PASS(?:ED)?\b", re.I)

    CONVERSATION_RE = re.compile(r"\b(?:you previously said|you just said|your previous answer|as you said|that earlier answer)\b", re.I)
    MEMORY_RE = re.compile(r"\b(?:persistent\s+)?memory\b[^.\n]{0,80}\b(?:contains|stored|saved|retrieved|recalls?)\b", re.I)
    WEB_RE = re.compile(r"\b(?:source|page|article|website)\b[^.\n]{0,100}\b(?:states|says|reports|confirms|supports)\b", re.I)
    CALC_RE = re.compile(r"\b(?:calculation|solver|calculationevidence|model)\b[^.\n]{0,90}\b(?:calculated|computed|shows|determined|verified)\b|\b(?:beam|section|design)\b[^.\n]{0,90}\b(?:satisfies|satisfied)\b[^.\n]{0,50}\b(?:deflection|stress|limit|constraint)\b", re.I)
    INFERENCE_RE = re.compile(r"\b(?:inference|i infer|we infer|probably|likely|may|might|appears to)\b", re.I)

    def validate(self, text: str, envelope: EvidenceEnvelope, *, conversation_context_available: bool = False) -> ValidationResult:
        unsupported: list[EvidenceClaim] = []
        provenance: list[EvidenceClaim] = []
        identifiers = envelope.receipt_ids()
        hashes = envelope.values("file_sha256") | envelope.values("content_sha256") | envelope.values("calculation_hash") | envelope.values("content_hash")
        paths = envelope.values("absolute_file_path") | envelope.values("cwd") | set(envelope.values("database_path"))
        for entry in envelope.receipts:
            receipt = entry.get("receipt", {})
            paths.update(str(path) for path in receipt.get("artifact_hashes", {}).keys())
        exit_codes = envelope.values("exit_code")
        calculation_ids = envelope.certified_calculation_ids()
        execution_ids = envelope.successful_execution_ids()
        memory_ids = {identifier for identifier in identifiers if identifier.startswith("memr_")}
        web_ids = {identifier for identifier in identifiers if identifier.startswith("web_")}

        def append(claim: EvidenceClaim, supported: bool) -> None:
            (provenance if supported else unsupported).append(claim)

        # Typed epistemic claims.  These do not use conversation text as a
        # substitute for execution, calculation, source, or memory authority.
        for match in self.CONVERSATION_RE.finditer(text):
            append(EvidenceClaim(match.group(0), "conversation_claim", (), ("conversation_context",), ("prior_turn",)), conversation_context_available)
        for match in self.MEMORY_RE.finditer(text):
            append(EvidenceClaim(match.group(0), "memory_claim", tuple(memory_ids), ("MemoryReceipt",), ("canonical_key", "content_hash")), bool(memory_ids))
        for match in self.WEB_RE.finditer(text):
            append(EvidenceClaim(match.group(0), "external_source_claim", tuple(web_ids), ("WebEvidence",), ("url", "content_sha256")), bool(web_ids))
        for match in self.CALC_RE.finditer(text):
            append(EvidenceClaim(match.group(0), "derived_scientific_claim", tuple(calculation_ids), ("CalculationEvidence",), ("derived_values", "residuals", "passed_oracles")), bool(calculation_ids))
        for match in self.INFERENCE_RE.finditer(text):
            # Inference is permitted but is explicitly typed in the internal
            # provenance so it cannot be mistaken for deterministic evidence.
            provenance.append(EvidenceClaim(match.group(0), "interpretive_inference", (), ("LLM_inference",), ()))

        for match in self.ID_RE.finditer(text):
            value = match.group(0); claim = EvidenceClaim(value, "receipt_id")
            (provenance if value in identifiers else unsupported).append(EvidenceClaim(value, "receipt_id", (value,) if value in identifiers else ()))
        for match in self.SHA_RE.finditer(text):
            value = match.group(0); (provenance if value in hashes else unsupported).append(EvidenceClaim(value, "hash", (value,) if value in hashes else ()))
        for match in self.PATH_RE.finditer(text):
            value = match.group(0).rstrip(".,;:")
            # Relative paths are compared against normalized absolute artifact endings.
            supported = value in paths or any(path.replace("\\", "/").endswith(value.replace("\\", "/")) for path in paths)
            (provenance if supported else unsupported).append(EvidenceClaim(value, "artifact_path", (value,) if supported else ()))
        for match in self.EXIT_RE.finditer(text):
            value = match.group(1); supported = value in exit_codes
            (provenance if supported else unsupported).append(EvidenceClaim(match.group(0), "exit_code", (value,) if supported else ()))

        verified = bool(calculation_ids or execution_ids)
        for match in self.CERT_RE.finditer(text):
            # A bare PASS is often normal prose; certified/verified and oracle/check PASS are evidence claims.
            supported = verified and ("pass" not in match.group(0).lower() or bool(calculation_ids))
            append(EvidenceClaim(match.group(0), "certification", tuple(calculation_ids or execution_ids) if supported else (), ("CalculationEvidence", "ExecutionEvidence"), ("certification_status", "passed_oracles")), supported)
        for match in self.EXEC_RE.finditer(text):
            phrase = match.group(0)
            # Explicit denials are not claims of completed work.
            if re.search(r"\b(?:not|no|never|cannot|did not|without evidence|unverified)\b", phrase, re.I):
                continue
            supported = bool(execution_ids)
            append(EvidenceClaim(phrase, "execution_claim", tuple(execution_ids) if supported else (), ("ExecutionEvidence",), ("exact_command", "exit_code", "artifact_hashes")), supported)

        for capability in envelope.capabilities:
            cid = str(capability.get("capability_id")); status = str(capability.get("runtime_status")); implementation = str(capability.get("implementation_status"))
            capability_match = re.search(rf"\b{re.escape(cid)}\b[^.\n]{{0,50}}\b(active|available|present|implemented|unavailable|blocked)\b", text, re.I)
            if capability_match:
                claimed = capability_match.group(1).lower()
                supported = ((claimed in {"active", "available", "present", "implemented"} and (status == "active" or implementation == "implemented"))
                             or (claimed in {"unavailable", "blocked"} and status == "unavailable"))
                claim = EvidenceClaim(cid, "runtime_capability_claim", (cid,) if supported else (), ("runtime_capability_registry",), ("runtime_status", "implementation_status"))
                append(claim, supported)

        return ValidationResult(not unsupported, tuple(unsupported), tuple(provenance))

    def reconcile(self, text: str, manifest: ClaimManifest, envelope: EvidenceEnvelope,
                  *, conversation_context_available: bool = False) -> ManifestAudit:
        """Reconcile emitted epistemic claims against the pre-generation manifest."""
        validation = self.validate(text, envelope, conversation_context_available=conversation_context_available)
        errors: list[str] = []
        if validation.unsupported_claims:
            errors.append("EVIDENCE_CLAIM_UNSUPPORTED")
        emitted: list[str] = []

        def type_for(claim: EvidenceClaim) -> str | None:
            mapping = {"execution_claim": "execution_claim", "execution_statement": "execution_claim",
                       "derived_scientific_claim": "derived_scientific_claim", "external_source_claim": "external_source_claim",
                       "memory_claim": "memory_claim", "runtime_capability_claim": "runtime_capability_claim",
                       "conversation_claim": "conversation_claim", "interpretive_inference": "interpretive_inference"}
            if claim.category == "receipt_id":
                return "execution_claim" if claim.text.startswith("exec_") else "derived_scientific_claim" if claim.text.startswith("calc_") else "external_source_claim" if claim.text.startswith("web_") else "memory_claim" if claim.text.startswith("memr_") else None
            return mapping.get(claim.category)

        for claim in validation.provenance:
            target_type = type_for(claim)
            if target_type is None:
                continue
            if target_type == "interpretive_inference":
                line_start = text.rfind("\n", 0, text.lower().find(claim.text.lower())) + 1
                if not text[line_start:].lstrip().lower().startswith("inference:"):
                    errors.append("INFERENCE_LABEL_MISSING")
            candidates = [entry for entry in manifest.entries if entry.claim_type == target_type]
            if target_type == "unavailable_claim":
                candidates = [entry for entry in candidates if entry.validation_status == "unavailable"]
            if claim.supported_by:
                candidates = [entry for entry in candidates if not entry.supporting_receipt_ids or set(claim.supported_by) & set(entry.supporting_receipt_ids)]
            if not candidates:
                errors.append("CLAIM_MANIFEST_MISMATCH")
            else:
                emitted.append(candidates[0].claim_id)

        # The explicit unavailable form can never be invented merely because a
        # generic tool is absent; it must map to a blocked action manifest entry.
        if "UNAVAILABLE_FOR_THIS_CLAIM" in text:
            unavailable = [entry for entry in manifest.entries if entry.claim_type == "unavailable_claim" and entry.validation_status == "unavailable"]
            if not unavailable:
                errors.append("CLAIM_MANIFEST_MISMATCH")
            else:
                emitted.append(unavailable[0].claim_id)

        # Qwen is never the audit authority.  If it nevertheless names a
        # manifest claim as audited, that claim must actually have been emitted.
        for audit_id in set(re.findall(r"\bclaim_\d{4}\b", text)):
            if audit_id not in emitted:
                errors.append("CLAIM_MANIFEST_MISMATCH")

        # A response that names two different receipt IDs of the same class in a
        # single assertion is ambiguous unless they were separately manifested.
        for prefix, kind in (("exec_", "execution_claim"), ("calc_", "derived_scientific_claim")):
            named = {match.group(0) for match in self.ID_RE.finditer(text) if match.group(0).startswith(prefix)}
            allowed = {identifier for entry in manifest.entries if entry.claim_type == kind for identifier in entry.supporting_receipt_ids}
            if len(named) > 1 and not named.issubset(allowed):
                errors.append("DUPLICATE_CONFLICTING_CLAIMS")

        # A calculation statement may not alter a stored number.  This compact
        # equivalence check accepts exact/round-trip numeric renderings only.
        if any(item.category == "derived_scientific_claim" for item in validation.provenance):
            numeric_values = self._calculation_numbers(envelope)
            relevant = self.CALC_RE.findall(text)
            for phrase in relevant:
                stripped = self.ID_RE.sub("", phrase)
                for token in re.findall(r"(?<![A-Za-z_])-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", stripped, re.I):
                    value = float(token)
                    if not any(abs(value - candidate) <= max(1e-10, abs(candidate) * 1e-9) for candidate in numeric_values):
                        errors.append("CLAIM_MANIFEST_MISMATCH")
                        break

        status = "passed" if not errors else errors[0]
        return ManifestAudit(status, tuple(dict.fromkeys(emitted)), tuple(dict.fromkeys(errors)))

    @staticmethod
    def _calculation_numbers(envelope: EvidenceEnvelope) -> set[float]:
        values: set[float] = set()
        def walk(value: Any) -> None:
            if isinstance(value, Mapping):
                for item in value.values(): walk(item)
            elif isinstance(value, tuple):
                for item in value: walk(item)
            elif isinstance(value, (int, float)) and not isinstance(value, bool): values.add(float(value))
        for entry in envelope.receipts:
            if entry.get("kind") == "calculation": walk(entry.get("receipt", {}))
        return values
