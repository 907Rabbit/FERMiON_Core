"""Typed llama.cpp server lifecycle. Generation is not a control-plane operation."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fermion.adapters.llama_cpp import LlamaCppConfig, LlamaServerRuntime, LlamaServerStatus
from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


class LlamaRuntimeAdapter(ApplicationInterface):
    """status/test are read-only; start/stop mutate the local server process only."""

    _CAPABILITIES = (
        CapabilityDefinition("status", False, True, "Report llama.cpp server configuration and health."),
        CapabilityDefinition("test", False, True, "Probe a loopback completion without treating it as authority."),
        CapabilityDefinition("start", True, True, "Start the configured loopback llama.cpp server."),
        CapabilityDefinition("stop", True, True, "Stop the FERMiON-managed llama.cpp server."),
    )

    def __init__(self, config: LlamaCppConfig | None = None, state_dir: str | Path = ".fermion") -> None:
        self.config = config or LlamaCppConfig()
        self.state_dir = Path(state_dir)
        self._runtime = LlamaServerRuntime(self.config, self.state_dir)

    def _status(self, *, network: bool = False) -> dict[str, Any]:
        if network:
            status = self._runtime.status()
        else:
            pid = self._runtime._pid()
            configured = bool(self.config.endpoint) or bool(self.config.server_executable and self.config.model_path)
            status = LlamaServerStatus(configured, bool(pid), False, pid, self.config.endpoint, self.config.model_path)
        return asdict(status)

    def observe(self) -> Observation:
        return Observation(time.time(), "llama_runtime", self._status(network=False), {"interface": "lifecycle"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("llama_runtime", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "status":
                return ActionResult(action.action_id, True, False, self._status(network=True))
            if action.operation == "test":
                probe = self._runtime.completion_probe() if hasattr(self._runtime, "completion_probe") else None
                return ActionResult(action.action_id, True, False, {**self._status(network=True), "completion": probe})
            if action.operation == "start":
                return ActionResult(action.action_id, True, True, asdict(self._runtime.start()))
            return ActionResult(action.action_id, True, True, asdict(self._runtime.stop()))
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        state = self.observe().state
        digest = hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        running = bool(checkpoint.logical_state.get("running"))
        try:
            if running:
                self._runtime.start()
            else:
                self._runtime.stop()
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            return RollbackResult(False, checkpoint.checkpoint_id, checkpoint.digest, str(error))
        return RollbackResult(True, checkpoint.checkpoint_id, self.checkpoint().digest)
