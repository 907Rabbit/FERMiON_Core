"""Verify-only scientific operations. Trajectory execution is not registered."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FermionScienceAdapter(ApplicationInterface):
    """Bundle/reference verification. CP10 full execution is intentionally absent."""

    _CAPABILITIES = (
        CapabilityDefinition("verify_cp10_bundle", False, True, "Verify the frozen CP10-P0.10 Oracle-A bundle."),
        CapabilityDefinition("verify_ai_g2s_manifest", False, True, "Verify an AI-G2S P1.1 source manifest."),
        CapabilityDefinition("reference_193", False, True, "Evaluate the frozen 193-parameter specimen once."),
    )

    def __init__(self, source_root: Path | None = None) -> None:
        self.source_root = (source_root or PROJECT_ROOT).resolve()

    def observe(self) -> Observation:
        return Observation(time.time(), "fermion_science", {
            "cp10_full_registered": False,
            "oracle_trajectory_authorized": False,
            "ai_g2s_full_matrix_registered": False,
            "source_root": str(self.source_root),
        })

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("fermion_science", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "verify_cp10_bundle":
                from fermion.cp10.oracle_a_launcher_p0_10 import verify
                return ActionResult(action.action_id, True, False, verify(self.source_root))
            if action.operation == "verify_ai_g2s_manifest":
                from fermion.ai_g1.ai_g2s_provenance import verify_preexecution_source_manifest
                manifest = Path(str(action.arguments.get("source_manifest",
                                                         self.source_root / "artifacts/ai_g2s_r1_1/source_manifest.json")))
                if not manifest.is_absolute():
                    manifest = self.source_root / manifest
                return ActionResult(action.action_id, True, False,
                                    verify_preexecution_source_manifest(root=self.source_root, manifest_path=manifest))
            from fermion.hr.reference_193 import FermionHR193, reference_inputs
            model = FermionHR193()
            trace = model(*reference_inputs())
            return ActionResult(action.action_id, True, False, {
                "parameter_count": model.parameter_count,
                "success": trace.success.detach().tolist(),
            })
        except (OSError, RuntimeError, ValueError, FileNotFoundError, TypeError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        state = self.observe().state
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
