"""Application-agnostic contracts and a deterministic Phase 17C.1 test adapter.

Adapters expose the legal observation and action surface.  They do not contain
planning or learned policy logic; that remains in the generic kernel.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .outcomes import ControlOutcome, classify_control_outcome


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Observation:
    timestamp: float
    application: str
    state: dict[str, Any]
    channels: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    reversible: bool
    idempotent: bool
    description: str = ""


@dataclass(frozen=True)
class CapabilitySet:
    application: str
    items: tuple[CapabilityDefinition, ...]

    def get(self, name: str) -> CapabilityDefinition | None:
        return next((item for item in self.items if item.name == name), None)


@dataclass(frozen=True)
class Action:
    operation: str
    arguments: dict[str, Any] = field(default_factory=dict)
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    success: bool
    changed: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    replayed: bool = False


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    expected_effect: dict[str, Any] | None
    observed_effect: dict[str, Any]
    reason: str = ""


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    logical_state: dict[str, Any]
    digest: str
    timestamp: float


@dataclass(frozen=True)
class RollbackResult:
    success: bool
    checkpoint_id: str
    restored_digest: str
    reason: str = ""


class ApplicationInterface(Protocol):
    def observe(self) -> Observation: ...
    def capabilities(self) -> CapabilitySet: ...
    def execute(self, action: Action) -> ActionResult: ...
    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult: ...
    def checkpoint(self) -> Checkpoint: ...
    def rollback(self, checkpoint: Checkpoint) -> RollbackResult: ...


class OwnershipAwareApplicationInterface(ApplicationInterface, Protocol):
    """Optional adapter extension: the kernel consults it before mutating actions."""
    def target_assessment(self): ...
    def is_mutating(self, action: Action) -> bool: ...


class AuditLog:
    """Append-only JSONL audit trail that can reconstruct a kernel episode."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, payload: Any) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(_canonical({"timestamp": time.time(), "event": event, "payload": asdict(payload)
                                      if hasattr(payload, "__dataclass_fields__") else payload}) + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


class DummyApplicationAdapter:
    """Small deterministic application state machine for kernel contract tests."""

    _CAPABILITIES = (
        CapabilityDefinition("increment", True, False, "Add an integer to the counter."),
        CapabilityDefinition("create_object", True, True, "Create a named object."),
        CapabilityDefinition("set_property", True, True, "Set an object property."),
        CapabilityDefinition("write_file", True, True, "Write an in-memory file."),
        CapabilityDefinition("delete_file", True, True, "Delete an in-memory file."),
        CapabilityDefinition("inject_failure", True, True, "Deterministically return a failed action."),
    )

    def __init__(self) -> None:
        self._state: dict[str, Any] = {"counter": 0, "objects": {}, "files": {}}
        self._idempotent_results: dict[str, ActionResult] = {}

    @staticmethod
    def _digest(state: dict[str, Any]) -> str:
        return hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest()

    def observe(self) -> Observation:
        return Observation(time.time(), "dummy", deepcopy(self._state), {"state_digest": self._digest(self._state)})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("dummy", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        capability = self.capabilities().get(action.operation)
        if capability is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        if capability.idempotent and action.idempotency_key in self._idempotent_results:
            previous = self._idempotent_results[action.idempotency_key]
            return ActionResult(action.action_id, previous.success, False, previous.details, previous.error, True)
        before = self._digest(self._state)
        try:
            if action.operation == "increment":
                self._state["counter"] += int(action.arguments.get("amount", 1))
            elif action.operation == "create_object":
                name = str(action.arguments["name"])
                self._state["objects"].setdefault(name, deepcopy(action.arguments.get("properties", {})))
            elif action.operation == "set_property":
                self._state["objects"][str(action.arguments["object"])][str(action.arguments["property"])] = deepcopy(action.arguments["value"])
            elif action.operation == "write_file":
                self._state["files"][str(action.arguments["path"])] = str(action.arguments["content"])
            elif action.operation == "delete_file":
                self._state["files"].pop(str(action.arguments["path"]), None)
            else:  # inject_failure
                return ActionResult(action.action_id, False, False, error="injected deterministic failure")
        except (KeyError, TypeError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")
        result = ActionResult(action.action_id, True, before != self._digest(self._state), {"state_digest": self._digest(self._state)})
        if capability.idempotent and action.idempotency_key is not None:
            self._idempotent_results[action.idempotency_key] = result
        return result

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = deepcopy(self._state)
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(observed.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed, "" if matches else "post-state differs from expectation")

    def checkpoint(self) -> Checkpoint:
        state = deepcopy(self._state)
        return Checkpoint(uuid.uuid4().hex, state, self._digest(state), time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        if self._digest(checkpoint.logical_state) != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self._digest(self._state), "checkpoint digest mismatch")
        self._state = deepcopy(checkpoint.logical_state)
        self._idempotent_results.clear()
        return RollbackResult(True, checkpoint.checkpoint_id, self._digest(self._state))


class WorldModel(Protocol):
    def predict(self, observation: Observation, action: Action) -> dict[str, Any] | None: ...


class DummyWorldModel:
    """Test-only deterministic transition model; the kernel only depends on WorldModel."""

    def predict(self, observation: Observation, action: Action) -> dict[str, Any] | None:
        state = deepcopy(observation.state)
        if action.operation == "increment":
            state["counter"] += int(action.arguments.get("amount", 1))
        elif action.operation == "write_file":
            state["files"][str(action.arguments["path"])] = str(action.arguments["content"])
        elif action.operation == "delete_file":
            state["files"].pop(str(action.arguments["path"]), None)
        elif action.operation == "create_object":
            state["objects"].setdefault(str(action.arguments["name"]), deepcopy(action.arguments.get("properties", {})))
        elif action.operation == "set_property":
            state["objects"][str(action.arguments["object"])][str(action.arguments["property"])] = deepcopy(action.arguments["value"])
        else:
            return None
        return state


@dataclass(frozen=True)
class TransitionRecord:
    before: Observation
    action: Action
    prediction: dict[str, Any] | None
    result: ActionResult
    verification: VerificationResult
    after: Observation
    novelty: bool
    model_mismatch: bool
    outcome: ControlOutcome


class ApplicationIntelligenceKernel:
    """Generic transition executor with capability checks, diagnostics, and audit."""

    def __init__(self, application: ApplicationInterface, world_model: WorldModel, audit: AuditLog):
        self.application, self.world_model, self.audit = application, world_model, audit

    def step(self, action: Action, expected_effect: dict[str, Any] | None = None) -> TransitionRecord:
        before = self.application.observe(); self.audit.record("observation_before", before)
        capability = self.application.capabilities().get(action.operation)
        prediction = self.world_model.predict(before, action) if capability else None
        assessment = getattr(self.application, "target_assessment", None)
        mutation = getattr(self.application, "is_mutating", None)
        if capability and callable(assessment) and callable(mutation):
            from .ownership import OwnershipGate
            decision = OwnershipGate.authorize(action, assessment(), mutating=mutation(action))
            if not decision.allowed:
                self.audit.record("ownership_veto", {"action": asdict(action), "reason": decision.reason})
                result = ActionResult(action.action_id, False, False, {"ownership_veto": True}, decision.reason)
            else:
                result = self.application.execute(action)
        else:
            result = (self.application.execute(action) if capability else
                      ActionResult(action.action_id, False, False, error="undeclared capability"))
        verification = self.application.verify(result, expected_effect)
        after = self.application.observe()
        mismatch = prediction is not None and prediction != after.state
        novelty = prediction is None or mismatch or not verification.success
        record = TransitionRecord(before, action, prediction, result, verification, after, novelty, mismatch,
                                  classify_control_outcome(result.success, result.error))
        self.audit.record("transition", record)
        return record
