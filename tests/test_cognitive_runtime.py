from pathlib import Path
import json

from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig


def test_memory_survives_between_runtime_instances(tmp_path: Path) -> None:
    config = RuntimeConfig(root=tmp_path)
    first = CognitiveRuntime(config)
    first.process("Remember that my experimental coefficient alpha is 0.37.")
    second = CognitiveRuntime(config)
    result = second.process("What coefficient did I use?")
    assert "0.37" in result.response
    assert result.energy["total"] >= 0


def test_cognitive_metrics_are_calculated(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    result = runtime.process("Explain Cahn-Hilliard mass conservation.")
    assert result.cognition["phenomenal_status"] == "indeterminate"
    assert result.cognition["conscious_access_proxy"] >= 0


def test_documented_prime_action_is_executed(tmp_path: Path) -> None:
    result = CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Create a Python program that calculates prime numbers and test it.")
    assert (tmp_path / "primes.py").is_file()
    assert "2" in result.response


def test_identity_uses_self_memory_not_unrelated_episodes(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.process("Explain Cahn-Hilliard mass conservation.")
    result = runtime.process("Hello. Tell me about yourself.")
    assert "FERMiON is a local cognitive AI system" in result.reasoning["answer_seed"]
    assert all("Cahn-Hilliard" not in memory for memory in result.reasoning["retrieved_memories"])


def test_execution_proof_is_executor_evidence_not_llm_text(tmp_path: Path) -> None:
    request = "Create workspace/ground_truth_test.py containing a program that prints exactly FERMION_EXECUTION_PROOF_918273. Actually execute it."
    result = CognitiveRuntime(RuntimeConfig(root=tmp_path)).process(request)
    payload = json.loads(result.response)
    assert payload["stdout"].strip() == "FERMION_EXECUTION_PROOF_918273"
    assert payload["exit_code"] == 0
    assert payload["file_sha256"]
    assert Path(payload["absolute_file_path"]).is_file()
    assert result.execution_evidence is not None


def test_semantic_memory_receipt_has_canonical_key(tmp_path: Path) -> None:
    result = CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Write the exact key FERMION_MEMORY_PROOF_918273 with value 0.371928 into persistent semantic memory.")
    payload = json.loads(result.response)
    assert payload["canonical_key"] == "FERMION_MEMORY_PROOF_918273"
    assert payload["stored_value"] == "0.371928"
    assert result.memory_receipt is not None


def test_receipts_survive_runtime_restart_and_verify_canonical_records(tmp_path: Path) -> None:
    config = RuntimeConfig(root=tmp_path)
    execution = CognitiveRuntime(config).process("Create workspace/ground_truth_test.py containing a program that prints exactly FERMION_EXECUTION_PROOF_918273. Actually execute it.")
    memory = CognitiveRuntime(config).process("Write the exact key FERMION_MEMORY_PROOF_918273 with value 0.371928 into persistent semantic memory.")
    restarted = CognitiveRuntime(config)
    execution_record = restarted.verify_execution(execution.execution_evidence.evidence_id)
    memory_record = restarted.verify_memory("FERMION_MEMORY_PROOF_918273")
    assert execution_record["receipt"]["evidence_id"] == execution.execution_evidence.evidence_id
    assert memory_record["stored_value"] == "0.371928"
    assert memory_record["memory_id"] == f"mem_{memory.memory_receipt.memory_id}"
    assert memory_record["content_hash"] == memory.memory_receipt.content_hash
