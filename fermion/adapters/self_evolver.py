"""Bounded control-plane adapter for the FERMiON safe self-evolver."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fermion.safe_self_evolver import EvolutionError, SafeSelfEvolver
from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


@dataclass(frozen=True)
class SelfEvolverConfig:
    workspace: Path
    max_generations: int = 120
    max_population: int = 128


class SelfEvolverAdapter(ApplicationInterface):
    """Expose only bounded, auditable evolver operations to the control plane."""

    _CAPABILITIES = (
        CapabilityDefinition("status", False, True, "Read the evolver's verified status."),
        CapabilityDefinition("record_feedback", True, False, "Record a bounded weighted regression example."),
        CapabilityDefinition("evolve", True, False, "Run one bounded, evidence-checked evolution cycle."),
        CapabilityDefinition("rollback", True, True, "Restore the prior promoted strategy version."),
    )

    def __init__(self, config: SelfEvolverConfig) -> None:
        self.config = config
        self.workspace = config.workspace.resolve()
        self.evolver = SafeSelfEvolver(self.workspace)
        self._checkpoints: dict[str, dict[str, bytes | None]] = {}

    @staticmethod
    def _digest(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()

    def _state(self) -> dict[str, Any]:
        return self.evolver.status()

    def _snapshot(self) -> dict[str, bytes | None]:
        paths = (self.evolver.active_path, self.evolver.state_path, self.evolver.feedback_path)
        snapshot = {str(path): path.read_bytes() if path.exists() else None for path in paths}
        for path in self.evolver.versions_path.glob("strategy_v*.py"):
            snapshot[str(path)] = path.read_bytes()
        return snapshot

    def observe(self) -> Observation:
        return Observation(time.time(), "safe-self-evolver", self._state(),
                           {"workspace": str(self.workspace), "scope": "generated strategy only"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("safe-self-evolver", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "status":
                return ActionResult(action.action_id, True, False, self._state())
            if action.operation == "record_feedback":
                result = self.evolver.record_feedback(float(action.arguments["x"]), float(action.arguments["target"]),
                                                       float(action.arguments.get("weight", 2.0)))
                return ActionResult(action.action_id, True, True, {"feedback": result, "executed": False})
            if action.operation == "evolve":
                seed = int(action.arguments.get("seed", 42))
                generations = int(action.arguments.get("generations", 40))
                population = int(action.arguments.get("population", 64))
                improvement = float(action.arguments.get("minimum_improvement", 0.001))
                if not 1 <= generations <= self.config.max_generations:
                    raise ValueError(f"generations must be 1..{self.config.max_generations}")
                if not 8 <= population <= self.config.max_population:
                    raise ValueError(f"population must be 8..{self.config.max_population}")
                if not 0.0 <= improvement < 1.0:
                    raise ValueError("minimum_improvement must be in [0, 1)")
                result = self.evolver.evolve(seed, generations, population, improvement)
                return ActionResult(action.action_id, True, True,
                                    {"result": result, "executed": False, "generated_strategy_scope": str(self.workspace)})
            result = self.evolver.rollback()
            return ActionResult(action.action_id, True, True, {"rollback": result, "executed": False})
        except (KeyError, OSError, TypeError, ValueError, EvolutionError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self._state()
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(observed.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed,
                                  "" if matches else "evolver post-state differs from expectation")

    def checkpoint(self) -> Checkpoint:
        checkpoint_id = uuid.uuid4().hex
        state = self._state()
        self._checkpoints[checkpoint_id] = self._snapshot()
        return Checkpoint(checkpoint_id, state, self._digest(state), time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        snapshot = self._checkpoints.pop(checkpoint.checkpoint_id, None)
        if snapshot is None or self._digest(checkpoint.logical_state) != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self._digest(self._state()), "checkpoint digest mismatch")
        current_versions = set(self.evolver.versions_path.glob("strategy_v*.py"))
        saved_versions = {Path(path) for path in snapshot if Path(path).parent == self.evolver.versions_path}
        for path in current_versions - saved_versions:
            path.unlink()
        for value, content in snapshot.items():
            path = Path(value)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
