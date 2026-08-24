"""Phase 17C.2 application transition encoding, diagnostics, and episode memory.

This module deliberately does not import or update the canonical FERMiON model.
It supplies application-independent diagnostic evidence which a future planner
may consult.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol

import torch

from fermion_symplectic_dysib import GSEDiagnosticHook
from fermion.hr.memory import EpisodicMemory, MemoryRecord, RetrievedMemory

from .application import (Action, ActionResult, ApplicationInterface, Checkpoint,
                          Observation, RollbackResult)


@dataclass(frozen=True)
class StateVector:
    values: tuple[float, ...]
    labels: tuple[str, ...]


@dataclass(frozen=True)
class StatePrediction:
    state: StateVector | None
    confidence: float
    known_transition: bool
    reason: str = ""


@dataclass(frozen=True)
class DiagnosticReport:
    prediction_error: float
    novelty_score: float
    mismatch_score: float
    transition_spike_score: float
    confidence: float
    failure_suspected: bool
    reasons: tuple[str, ...]
    delta_g: float
    invariants: tuple[float, float, float, float]
    metric_mismatch: float
    curvature_proxy: float


class StateEncoder(Protocol):
    def encode(self, observation: Observation) -> StateVector: ...


class TransitionModel(Protocol):
    def predict(self, state: StateVector, action: Action) -> StatePrediction: ...
    def update(self, transition: "EpisodeStep") -> None: ...


class DiagnosticEngine(Protocol):
    def evaluate(self, state: StateVector, action: Action, prediction: StatePrediction,
                 actual_state: StateVector, result: ActionResult) -> DiagnosticReport: ...


class DummyStateEncoder:
    """Deterministic features for the 17C.1 dummy environment, not a learned encoder."""

    _LABELS = ("counter", "object_count", "property_count", "file_count", "file_bytes")

    def encode(self, observation: Observation) -> StateVector:
        state = observation.state
        objects = state.get("objects", {})
        files = state.get("files", {})
        return StateVector((float(state.get("counter", 0)), float(len(objects)),
                            float(sum(len(properties) for properties in objects.values())),
                            float(len(files)), float(sum(len(content) for content in files.values()))), self._LABELS)


class DummyTransitionModel:
    """Known deterministic transitions used only to prove diagnostic plumbing."""

    def predict(self, state: StateVector, action: Action) -> StatePrediction:
        values = list(state.values)
        if action.operation == "increment":
            values[0] += float(action.arguments.get("amount", 1))
        elif action.operation == "write_file":
            # Exact file mutation cannot be inferred from aggregate features without history.
            return StatePrediction(None, 0.25, False, "file content identity is not modeled")
        else:
            return StatePrediction(None, 0.0, False, f"unseen operation: {action.operation}")
        return StatePrediction(StateVector(tuple(values), state.labels), 1.0, True)

    def update(self, transition: "EpisodeStep") -> None:
        # Intentional no-op baseline; learned models can implement this protocol later.
        return None


class GSEDiagnosticEngine:
    """Structured, non-policy diagnostic projection of application transitions."""

    def __init__(self) -> None:
        self._previous_error = 0.0
        self._trajectory: list[tuple[float, ...]] = []
        self._gse_hook = GSEDiagnosticHook()

    def evaluate(self, state: StateVector, action: Action, prediction: StatePrediction,
                 actual_state: StateVector, result: ActionResult) -> DiagnosticReport:
        if prediction.state is None:
            error = 1.0
            mismatch = 1.0
        else:
            squared = sum((actual - expected) ** 2 for actual, expected in zip(actual_state.values, prediction.state.values))
            error = math.sqrt(squared / max(1, len(actual_state.values)))
            mismatch = min(1.0, error)
        novelty = 0.0 if prediction.known_transition and error == 0.0 else 1.0 - prediction.confidence
        if not result.success:
            novelty, mismatch = max(novelty, 1.0), max(mismatch, 1.0)
        spike = max(0.0, error - self._previous_error)
        self._previous_error = error
        self._trajectory.append(actual_state.values)
        # The canonical GSE hook is applicable only after a three-state trajectory.
        # Before then the residual signals remain explicit rather than fabricated.
        if len(self._trajectory) >= 3:
            latent = torch.tensor([self._trajectory[-64:]], dtype=torch.float32)
            gse = self._gse_hook(latent)
            delta_g = gse.Delta_G_norm
            invariants = (gse.I1, gse.I2, gse.I3, gse.I4)
            curvature = gse.curvature_proxy
            spike = max(spike, gse.transition_spike_score)
        else:
            delta_g = error + novelty + spike
            invariants = (error, novelty, mismatch, spike)
            curvature = spike
        reasons = []
        if not prediction.known_transition: reasons.append(prediction.reason or "unseen transition")
        if mismatch: reasons.append("prediction residual")
        if not result.success: reasons.append(result.error or "action failure")
        return DiagnosticReport(error, novelty, mismatch, spike, prediction.confidence,
                                not result.success or mismatch > 0.5,
                                tuple(reasons), delta_g, invariants, mismatch, curvature)


@dataclass(frozen=True)
class EpisodeStep:
    step_id: str
    parent_step_id: str | None
    branch_id: str
    timestamp: float
    state: StateVector
    action: Action
    prediction: StatePrediction
    actual_state: StateVector
    result: ActionResult
    diagnostic: DiagnosticReport


class ApplicationEpisodicMemory:
    """Branch-aware facade over the existing persistent episodic-memory store."""

    def __init__(self, memory: EpisodicMemory):
        self.memory = memory

    def append(self, step: EpisodeStep) -> int | None:
        payload = asdict(step)
        return self.memory.write(MemoryRecord(
            step.state.values, step.actual_state.values, {"state": asdict(step.state)},
            {"action": asdict(step.action), "episode": payload},
            {"result": asdict(step.result), "diagnostic": asdict(step.diagnostic)},
            {"parent_step_id": step.parent_step_id, "branch_id": step.branch_id},
            float(step.result.success), step.diagnostic.confidence, step.timestamp),
            novelty=step.diagnostic.novelty_score, energy_change=step.diagnostic.delta_g,
            information_gain=1.0, failure_significance=float(step.diagnostic.failure_suspected), threshold=0.0)

    def retrieve_similar(self, state: StateVector, action: Action | None = None) -> list[RetrievedMemory]:
        matches = self.memory.retrieve(state.values)
        if action is None:
            return matches
        return [match for match in matches if match.record.action.get("action", {}).get("operation") == action.operation]


class DiagnosticTransitionLayer:
    """Observe → encode → predict → act → diagnose → remember orchestration."""

    def __init__(self, application: ApplicationInterface, encoder: StateEncoder,
                 model: TransitionModel, diagnostics: DiagnosticEngine,
                 memory: ApplicationEpisodicMemory):
        self.application, self.encoder, self.model = application, encoder, model
        self.diagnostics, self.memory = diagnostics, memory
        self._last_step_id: str | None = None
        self._branch_id = "root"

    def step(self, action: Action) -> EpisodeStep:
        before = self.application.observe(); state = self.encoder.encode(before)
        prediction = self.model.predict(state, action)
        result = self.application.execute(action)
        actual_state = self.encoder.encode(self.application.observe())
        diagnostic = self.diagnostics.evaluate(state, action, prediction, actual_state, result)
        step = EpisodeStep(uuid.uuid4().hex, self._last_step_id, self._branch_id, time.time(), state,
                           action, prediction, actual_state, result, diagnostic)
        self.memory.append(step); self.model.update(step); self._last_step_id = step.step_id
        return step

    def checkpoint(self) -> Checkpoint:
        return self.application.checkpoint()

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        result = self.application.rollback(checkpoint)
        if result.success:
            # The failed path remains persisted; future steps are explicitly linked to a new branch.
            self._branch_id = uuid.uuid4().hex
        return result
