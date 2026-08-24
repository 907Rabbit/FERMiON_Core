"""End-to-end Software Learning Kernel orchestration."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import torch
from torch import Tensor

from fermion.hr.contracts import CandidateProgram, DecisionTrace, ExecutionResult, HRState
from fermion.hr.memory import EpisodicMemory, MemoryRecord
from fermion.hr.system import FermionHR

from .executor import GuardedExecutor, PolicyViolation
from .observation import ObservationBus, ObservationSnapshot
from .ownership import OwnershipGate
from .replay import ReplayDatabase, ReplayRecord
from .validators import Validator


@dataclass(frozen=True)
class KernelResult:
    execution: ExecutionResult
    decision: DecisionTrace
    state: HRState


class ObservationProjector:
    """Stable hashing baseline that maps raw observations into model channels."""

    def __init__(self, model: FermionHR):
        self.model = model

    @staticmethod
    def _vector(payload: Any, dimension: int) -> Tensor:
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        values = []
        for index in range(dimension):
            digest = hashlib.blake2b(encoded + index.to_bytes(4, "little"), digest_size=8).digest()
            integer = int.from_bytes(digest, "little")
            values.append((integer / (2**64 - 1)) * 2.0 - 1.0)
        return torch.tensor([values], dtype=torch.float32)

    def project(self, goal: str, snapshot: ObservationSnapshot) -> dict[str, Tensor | None]:
        dimensions = self.model.config.modality_dims
        payloads = {
            "text": goal,
            "vision": snapshot.channels.get("vision"),
            "structured": snapshot.channels,
            "tools": snapshot.channels.get("tools"),
            "history": {"errors": snapshot.provider_errors, "timestamp": snapshot.timestamp},
        }
        return {name: (None if payloads.get(name) is None else self._vector(payloads[name], size))
                for name, size in dimensions.items()}


class SoftwareLearningKernel:
    def __init__(self, model: FermionHR, observation_bus: ObservationBus,
                 executor: GuardedExecutor, replay: ReplayDatabase,
                 episodic_memory: EpisodicMemory):
        self.model = model
        self.observation_bus = observation_bus
        self.executor = executor
        self.replay = replay
        self.episodic_memory = episodic_memory
        self.projector = ObservationProjector(model)
        self.state = model.initial_state()

    def close(self) -> None:
        self.replay.close()
        self.episodic_memory.close()

    def run(self, goal: str, candidates: list[CandidateProgram], validator: Validator,
            *, commit: bool = False) -> KernelResult:
        eligible = []
        violations = {}
        for candidate in candidates:
            try:
                self.executor.inspect(candidate)
                eligible.append(candidate)
            except PolicyViolation as error:
                violations[candidate.candidate_id] = str(error)
        if not eligible:
            raise PolicyViolation(f"no eligible candidates: {violations}")
        before = self.observation_bus.observe()
        observations = self.projector.project(goal, before)
        features = self.model.candidate_features(eligible)
        costs = torch.tensor([[candidate.estimated_cost for candidate in eligible]], dtype=torch.float32)
        risks = torch.tensor([[candidate.estimated_risk for candidate in eligible]], dtype=torch.float32)
        self.model.eval()
        with torch.no_grad():
            decision = self.model(observations, self.state, features, costs, risks,
                                  candidate_contracts=eligible)
        if decision.trace is None:
            raise RuntimeError("kernel currently requires a single observation batch")
        selected = eligible[int(decision.selected_index.item())]
        execution = self.executor.execute(selected, validator, commit=commit)
        raw_after = self.observation_bus.observe()
        after = ObservationSnapshot(raw_after.timestamp,
                                    {**raw_after.channels, "execution": asdict(execution)},
                                    raw_after.provider_errors)
        next_observations = self.projector.project(goal, after)
        with torch.no_grad():
            self.state = self.model.update_state(self.state, decision, next_observations, execution.validator)
        self._record(goal, candidates, before, after, decision.trace, execution, violations,
                     decision.encoded.detach().reshape(-1).tolist())
        return KernelResult(execution, decision.trace, self.state.detached())

    def _record(self, goal: str, candidates: list[CandidateProgram], before: ObservationSnapshot,
                after: ObservationSnapshot, decision: DecisionTrace, execution: ExecutionResult,
                violations: dict[str, str], memory_key: list[float]) -> None:
        candidate_payloads = [asdict(candidate) for candidate in candidates]
        for item in candidate_payloads:
            item["kind"] = item["kind"].value
        execution_payload = asdict(execution)
        self.replay.append(ReplayRecord(goal, candidate_payloads, execution.candidate_id,
                                        asdict(before), asdict(after), execution_payload,
                                        {**asdict(decision), "policy_violations": violations}, time.time()))
        self.episodic_memory.write(MemoryRecord(
            tuple(memory_key), tuple(self.state.memory.detach().reshape(-1).tolist()),
            asdict(before), {"candidate_id": execution.candidate_id}, execution_payload,
            {"recovered": execution.recovered}, execution.validator.information,
            execution.validator.success, time.time()),
            novelty=1.0, information_gain=execution.validator.information,
            failure_significance=float(execution.validator.success < 0.5))
