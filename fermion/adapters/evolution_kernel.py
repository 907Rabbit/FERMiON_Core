"""Bounded LLM-facing adapter for the separate CW-71 simulation kernel."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fermion import self_evolution_kernel as kernel_module
from fermion.self_evolution_kernel import FERMiONKernel
from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


@dataclass(frozen=True)
class EvolutionKernelConfig:
    workspace: Path
    max_cycles: int = 100


class EvolutionKernelAdapter(ApplicationInterface):
    """Expose deterministic, in-memory CW-71 simulations without replacing the safe evolver."""

    _CAPABILITIES = (
        CapabilityDefinition("status", False, True, "Describe the separate CW-71 kernel and its bounds."),
        CapabilityDefinition("simulate", False, False,
                             "Run a bounded deterministic self-evolution simulation and return its evidence."),
    )

    def __init__(self, config: EvolutionKernelConfig) -> None:
        if isinstance(config.max_cycles, bool) or not isinstance(config.max_cycles, int) or config.max_cycles < 1:
            raise ValueError("max_cycles must be a positive integer")
        self.config = config
        self.workspace = config.workspace.resolve()
        self.source_path = Path(kernel_module.__file__).resolve()
        self.source_sha256 = hashlib.sha256(self.source_path.read_bytes()).hexdigest().upper()
        self._last_simulation: dict[str, Any] | None = None
        self._checkpoints: dict[str, dict[str, Any] | None] = {}

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest().upper()

    def _state(self) -> dict[str, Any]:
        return {
            "engine": "CW-71 falsifiable self-evolution simulation",
            "module_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "max_cycles": self.config.max_cycles,
            "separate_from_safe_self_evolver": True,
            "adapter_mode": "bounded deterministic in-memory simulation",
            "last_simulation": self._last_simulation,
        }

    @staticmethod
    def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer from {minimum} through {maximum}")
        return value

    def observe(self) -> Observation:
        return Observation(time.time(), "self-evolution-kernel", self._state(), {
            "workspace": str(self.workspace),
            "persistence": "none in adapter mode",
            "existing_safe_evolver_replaced": False,
        })

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("self-evolution-kernel", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "status":
                return ActionResult(action.action_id, True, False, self._state())
            cycles = self._integer(action.arguments.get("cycles"), "cycles", 1, self.config.max_cycles)
            seed = self._integer(action.arguments.get("seed", 42), "seed", 0, 2**32 - 1)
            kernel = FERMiONKernel(seed=seed, workspace=self.workspace)
            result = kernel.run_evolution(cycles, verbose=False)
            manifests = kernel.promoted_candidates + kernel.rejected_candidates
            last_manifest = max(manifests, key=lambda item: item.candidate_id).to_dict() if manifests else None
            summary = {
                "seed": seed,
                "total_cycles": result["total_cycles"],
                "promoted": result["promoted"],
                "rejected": result["rejected"],
                "success_rate": result["success_rate"],
                "final_task_loss": result["final_task_loss"],
                "final_classification_loss": result["final_classification_loss"],
                "final_grounding_loss": result["final_grounding_loss"],
                "self_model_calibration_error": result["self_model_calibration_error"],
                "self_model_directional_accuracy": result["self_model_directional_accuracy"],
                "audit_chain_verified": result["audit_chain_verified"],
                "validator_hash": result["validator_hash"],
                "dataset_hashes": result["dataset_hashes"],
                "active_version": kernel.active_version,
                "active_sha256": kernel.active_sha256,
                "last_candidate_manifest": last_manifest,
            }
            self._last_simulation = summary
            return ActionResult(action.action_id, True, True, {
                "simulation": summary,
                "source_sha256": self.source_sha256,
                "executed": True,
                "persistent_outputs_created": False,
            })
        except (KeyError, OSError, TypeError, ValueError, OverflowError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self._state()
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            simulation = result.details.get("simulation")
            verified = simulation is None or simulation.get("audit_chain_verified") is True
            return VerificationResult(verified, None, observed,
                                      "" if verified else "kernel audit-chain verification failed")
        matches = all(observed.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed,
                                  "" if matches else "kernel post-state differs from expectation")

    def checkpoint(self) -> Checkpoint:
        checkpoint_id = uuid.uuid4().hex
        snapshot = json.loads(json.dumps(self._last_simulation)) if self._last_simulation is not None else None
        self._checkpoints[checkpoint_id] = snapshot
        state = self._state()
        return Checkpoint(checkpoint_id, state, self._digest(state), time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        if checkpoint.checkpoint_id not in self._checkpoints:
            return RollbackResult(False, checkpoint.checkpoint_id, self._digest(self._state()),
                                  "checkpoint not found")
        self._last_simulation = self._checkpoints.pop(checkpoint.checkpoint_id)
        return RollbackResult(True, checkpoint.checkpoint_id, self._digest(self._state()))
