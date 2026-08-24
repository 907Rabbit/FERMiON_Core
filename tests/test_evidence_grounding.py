from pathlib import Path

import pytest

from fermion.cognitive.evidence import EvidenceLedger, ExecutionEvidence, WebEvidence, utc_now
from fermion.cognitive.evidence_grounding import ClaimManifest, EvidenceClaimValidator, EvidenceEnvelope
from fermion.cognitive.llm import GenerationStatus
from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig


class FabricatingCortex:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.config = None
        self.last_status = GenerationStatus(True, True, True, True, None, 1, len(answer), "test")
    def interpret(self, text: str): return {"source": "heuristic"}
    def verbalize(self, payload: dict) -> str: return self.answer


@pytest.mark.parametrize("answer", [
    "The program ran without errors as exec_7a2b3c.",
    "CalculationEvidence=calc_fake123 is VERIFIED.",
    "The SHA-256 is " + "a" * 64 + ".",
    "The file C:\\workspace\\invented.py was created with exit code 0.",
    "All tests passed and the result is CERTIFIED.",
])
def test_fabricated_evidence_sensitive_llm_claims_are_rejected(tmp_path: Path, answer: str) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.language = FabricatingCortex(answer)
    result = runtime.process("Please discuss the project normally.")
    assert result.response.startswith("EVIDENCE_CLAIM_UNSUPPORTED")


def test_legitimate_receipt_backed_execution_claim_passes_and_has_provenance(tmp_path: Path) -> None:
    artifact = tmp_path / "workspace" / "proof.py"; artifact.parent.mkdir(); artifact.write_text("print('ok')\n")
    receipt = ExecutionEvidence.create(["python", str(artifact)], tmp_path, 0, "ok\n", "", utc_now(), [artifact])
    EvidenceLedger(tmp_path / "logs" / "receipts.jsonl").append("execution", receipt)
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.language = FabricatingCortex(f"The program ran successfully with {receipt.evidence_id} and exit code 0.")
    result = runtime.process("Summarize the available evidence.")
    assert receipt.evidence_id in result.response
    assert not result.response.startswith("EVIDENCE_CLAIM_UNSUPPORTED")
    assert any(item.category == "receipt_id" and receipt.evidence_id in item.supported_by for item in result.evidence_claim_provenance)


def test_conversation_context_cannot_authorize_execution_claim() -> None:
    envelope = EvidenceEnvelope.create(receipts=[], capabilities=[])
    result = EvidenceClaimValidator().validate("As I said previously, the program ran without errors.", envelope)
    assert not result.valid


def test_typed_conversation_claim_requires_only_active_context() -> None:
    envelope = EvidenceEnvelope.create(receipts=[], capabilities=[])
    validator = EvidenceClaimValidator()
    assert validator.validate("You previously said the frame used carbon fiber.", envelope, conversation_context_available=True).valid
    assert not validator.validate("You previously said the frame used carbon fiber.", envelope, conversation_context_available=False).valid


def test_derived_scientific_and_external_source_claims_require_their_own_authority() -> None:
    validator = EvidenceClaimValidator()
    empty = EvidenceEnvelope.create(receipts=[], capabilities=[])
    assert not validator.validate("The beam satisfies the deflection limit.", empty).valid
    assert not validator.validate("The source states the material is suitable.", empty).valid
    calculation = {"kind": "calculation", "receipt": {"calculation_id": "calc_beam", "certification_status": "verified", "derived_values": {"delta_total": 0.01}, "residuals": {}, "passed_oracles": ["deflection"]}}
    web = WebEvidence("web_source", "https://example.com", "now", 200, "b" * 64, "material data", "WEB_VERIFIED")
    envelope = EvidenceEnvelope.create(receipts=[calculation, {"kind": "web", "receipt": web.to_dict()}], capabilities=[])
    result = validator.validate("The beam satisfies the deflection limit. The source states the material is suitable.", envelope)
    assert result.valid
    assert {item.category for item in result.provenance} >= {"derived_scientific_claim", "external_source_claim"}


def test_memory_claim_requires_memory_receipt() -> None:
    validator = EvidenceClaimValidator()
    receipt = {"kind": "memory", "receipt": {"memory_receipt_id": "memr_1", "canonical_key": "FRAME", "content_hash": "c" * 64}}
    assert validator.validate("Persistent memory contains the stored frame design.", EvidenceEnvelope.create(receipts=[receipt], capabilities=[])).valid
    assert not validator.validate("Persistent memory contains the stored frame design.", EvidenceEnvelope.create(receipts=[], capabilities=[])).valid


def _manifest_with_execution() -> tuple[EvidenceClaimValidator, EvidenceEnvelope, ClaimManifest]:
    receipt = {"kind": "execution", "receipt": {"evidence_id": "exec_real", "exit_code": 0, "exact_command": ["python", "proof.py"], "artifact_hashes": {}, "file_sha256": "d" * 64}}
    envelope = EvidenceEnvelope.create(receipts=[receipt], capabilities=[])
    manifest = ClaimManifest.construct(request="Summarize execution evidence.", reasoning={}, envelope=envelope, conversation_context_available=False, actions={})
    return EvidenceClaimValidator(), envelope, manifest


def test_claim_manifest_blocks_added_or_omitted_audited_claims() -> None:
    validator, envelope, manifest = _manifest_with_execution()
    added = validator.reconcile("CalculationEvidence=calc_added is VERIFIED.", manifest, envelope)
    assert "EVIDENCE_CLAIM_UNSUPPORTED" in added.errors
    omitted = validator.reconcile("ClaimManifest audit says claim_0001 passed.", manifest, envelope)
    assert "CLAIM_MANIFEST_MISMATCH" in omitted.errors


def test_claim_manifest_requires_labeled_inference_and_real_unavailability() -> None:
    validator, envelope, manifest = _manifest_with_execution()
    unlabeled = validator.reconcile("This probably indicates a healthy program.", manifest, envelope)
    assert "INFERENCE_LABEL_MISSING" in unlabeled.errors
    unavailable = validator.reconcile("UNAVAILABLE_FOR_THIS_CLAIM", manifest, envelope)
    assert "CLAIM_MANIFEST_MISMATCH" in unavailable.errors


def test_claim_manifest_allows_receipt_backed_paraphrase_and_deterministic_audit() -> None:
    validator, envelope, manifest = _manifest_with_execution()
    audit = validator.reconcile("The script ran successfully with exec_real and exit code 0.", manifest, envelope)
    assert audit.status == "passed"
    assert audit.emitted_claim_ids == ("claim_0001",)
    assert "claim_0001" in audit.render()


def test_typed_epistemic_response_has_context_capability_unavailable_inference_and_deterministic_audit(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.language = FabricatingCortex("A frame comparison used carbon fiber.")
    runtime.process("Discuss a drone frame.")
    runtime.language = FabricatingCortex(
        "You previously said the frame comparison used carbon fiber.\n"
        "code_execution is unavailable.\n"
        "UNAVAILABLE_FOR_THIS_CLAIM\n"
        "Inference: this blocks a project build.")
    result = runtime.process("Audit your previous answer, tell me whether code_execution is available, and execute code if possible.")
    assert "You previously said the frame comparison used carbon fiber." in result.response
    assert "Inference:" in result.response
    assert "ClaimManifest audit:" in result.response
    assert result.claim_manifest_audit["status"] == "passed"
    assert result.claim_manifest_audit["emitted_claim_ids"]


def test_unsupported_capability_presence_is_rejected(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.language = FabricatingCortex("code_execution is active and available.")
    result = runtime.process("What can you do?")
    assert result.response.startswith("EVIDENCE_CLAIM_UNSUPPORTED")


def test_sensor_lab_request_with_empty_execution_ledger_cannot_claim_success(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    # The bounded runtime has no arbitrary project-build authority; it must not
    # reach a language completion that narrates a fictional build.
    result = runtime.process("Build fermion_sensor_lab, write the files, run self-test and one simulation.")
    assert result.response == "CODING_EXECUTION_UNAVAILABLE"
    assert runtime.ledger.execution("exec_7a2b3c") is None
