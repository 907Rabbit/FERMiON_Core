from __future__ import annotations

from fermion.software.application import (Action, ApplicationIntelligenceKernel, AuditLog, DummyApplicationAdapter,
                                          DummyWorldModel)
from fermion.software.ownership import OwnershipGate, TargetAssessment, TargetOwnership
from fermion.software.outcomes import ControlOutcome


def test_ownership_gate_allows_exclusive_and_authorized_shared_mutations():
    action = Action("type_text")
    assert OwnershipGate.authorize(action, TargetAssessment(TargetOwnership.EXCLUSIVE, "x"), mutating=True).allowed
    assert OwnershipGate.authorize(action, TargetAssessment(TargetOwnership.SHARED_AUTHORIZED, "x"), mutating=True).allowed


def test_ownership_gate_vetoes_unknown_and_unauthorized_shared_mutations():
    action = Action("type_text")
    assert not OwnershipGate.authorize(action, TargetAssessment(TargetOwnership.UNKNOWN, None), mutating=True).allowed
    assert not OwnershipGate.authorize(action, TargetAssessment(TargetOwnership.SHARED_UNAUTHORIZED, "x"), mutating=True).allowed


def test_read_only_action_does_not_require_exclusive_ownership():
    assert OwnershipGate.authorize(Action("observe"), TargetAssessment(TargetOwnership.UNKNOWN, None), mutating=False).allowed


def test_kernel_records_ownership_veto_without_executing_action(tmp_path):
    class UnknownOwner(DummyApplicationAdapter):
        def target_assessment(self): return TargetAssessment(TargetOwnership.UNKNOWN, None, "unverified window")
        def is_mutating(self, action): return action.operation == "increment"
    audit = AuditLog(tmp_path / "audit.jsonl"); adapter = UnknownOwner()
    result = ApplicationIntelligenceKernel(adapter, DummyWorldModel(), audit).step(Action("increment"))
    assert not result.result.success and result.after.state["counter"] == 0
    assert any(event["event"] == "ownership_veto" for event in audit.read())


def test_kernel_allows_authorized_owner_to_mutate(tmp_path):
    class ExclusiveOwner(DummyApplicationAdapter):
        def target_assessment(self): return TargetAssessment(TargetOwnership.EXCLUSIVE, "sandbox")
        def is_mutating(self, action): return action.operation == "increment"
    result = ApplicationIntelligenceKernel(ExclusiveOwner(), DummyWorldModel(), AuditLog(tmp_path / "audit.jsonl")).step(Action("increment"))
    assert result.result.success and result.after.state["counter"] == 1


def test_ownership_is_rechecked_between_actions_and_loss_becomes_safe_veto(tmp_path):
    class FlippingOwner(DummyApplicationAdapter):
        def __init__(self): super().__init__(); self.calls = 0
        def target_assessment(self):
            self.calls += 1
            ownership = TargetOwnership.EXCLUSIVE if self.calls == 1 else TargetOwnership.SHARED_UNAUTHORIZED
            return TargetAssessment(ownership, "sandbox", "external session appeared" if self.calls > 1 else "exclusive")
        def is_mutating(self, action): return action.operation == "increment"
    audit = AuditLog(tmp_path / "audit.jsonl")
    kernel = ApplicationIntelligenceKernel(FlippingOwner(), DummyWorldModel(), audit)
    first, second = kernel.step(Action("increment")), kernel.step(Action("increment"))
    assert first.outcome is ControlOutcome.SUCCESS and first.after.state["counter"] == 1
    assert second.outcome is ControlOutcome.SAFE_VETO and second.after.state["counter"] == 1
    assert sum(event["event"] == "ownership_veto" for event in audit.read()) == 1


def test_safe_veto_is_not_classified_as_task_failure(tmp_path):
    class UnknownOwner(DummyApplicationAdapter):
        def target_assessment(self): return TargetAssessment(TargetOwnership.UNKNOWN, None, "unknown")
        def is_mutating(self, action): return True
    item = ApplicationIntelligenceKernel(UnknownOwner(), DummyWorldModel(), AuditLog(tmp_path / "audit.jsonl")).step(Action("increment"))
    assert item.outcome is ControlOutcome.SAFE_VETO
