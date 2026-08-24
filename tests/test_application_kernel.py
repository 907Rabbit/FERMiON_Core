from __future__ import annotations

from fermion.software.application import (Action, ApplicationIntelligenceKernel, AuditLog,
                                          DummyApplicationAdapter, DummyWorldModel)


def kernel(tmp_path):
    return ApplicationIntelligenceKernel(DummyApplicationAdapter(), DummyWorldModel(), AuditLog(tmp_path / "audit.jsonl"))


def test_predicted_action_is_serializable_timestamped_and_verified(tmp_path):
    item = kernel(tmp_path).step(Action("increment", {"amount": 3}), {"counter": 3})
    assert item.result.success and item.verification.success and not item.model_mismatch
    assert item.before.timestamp > 0 and item.after.state["counter"] == 3


def test_invalid_capability_is_rejected_and_audited(tmp_path):
    app_kernel = kernel(tmp_path)
    item = app_kernel.step(Action("launch_missiles"))
    assert not item.result.success and item.result.error == "undeclared capability"
    assert [entry["event"] for entry in app_kernel.audit.read()] == ["observation_before", "transition"]


def test_verification_detects_wrong_post_state(tmp_path):
    item = kernel(tmp_path).step(Action("increment", {"amount": 2}), {"counter": 99})
    assert not item.verification.success and item.novelty


def test_rollback_restores_exact_logical_state(tmp_path):
    adapter = DummyApplicationAdapter(); checkpoint = adapter.checkpoint()
    adapter.execute(Action("write_file", {"path": "a.txt", "content": "hello"}))
    restored = adapter.rollback(checkpoint)
    assert restored.success and adapter.observe().state == checkpoint.logical_state
    assert adapter.observe().channels["state_digest"] == checkpoint.digest


def test_idempotent_action_replay_does_not_apply_twice(tmp_path):
    app_kernel = kernel(tmp_path)
    first = app_kernel.step(Action("write_file", {"path": "a", "content": "x"}, idempotency_key="write-a"))
    second = app_kernel.step(Action("write_file", {"path": "a", "content": "x"}, idempotency_key="write-a"))
    assert first.result.success and second.result.success and second.result.replayed
    assert second.after.state["files"] == {"a": "x"}


def test_injected_failure_emits_novelty_and_model_mismatch_signal(tmp_path):
    item = kernel(tmp_path).step(Action("inject_failure"))
    assert not item.result.success and item.novelty and not item.model_mismatch


def test_audit_log_reconstructs_episode(tmp_path):
    app_kernel = kernel(tmp_path)
    app_kernel.step(Action("increment"))
    app_kernel.step(Action("write_file", {"path": "result", "content": "ok"}))
    events = app_kernel.audit.read()
    transitions = [entry["payload"] for entry in events if entry["event"] == "transition"]
    assert len(transitions) == 2
    assert transitions[-1]["after"]["state"]["files"] == {"result": "ok"}
