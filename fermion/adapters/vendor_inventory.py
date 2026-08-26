"""Read-only inventory of vendored trees that are not FERMiON adapters."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fermion.source_exclusions import EXCLUDED_DIRECTORY_NAMES
from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

VENDOR_PURPOSE = {
    "bettercap": "Network attack/recon framework; not an adapter.",
    "Ciphey": "Automated decoder; not an adapter.",
    "CL4R1T4S": "Extracted third-party system prompts; not an adapter.",
    "codex": "Independent coding agent; not a FERMiON tool.",
    "GhostTrack": "Phone/IP tracker; not an adapter.",
    "hackingtool": "Security-tool aggregator; not an adapter.",
    "spiderfoot": "OSINT scanner; not a live adapter.",
    "the-book-of-secret-knowledge": "Cheatsheet collection; not an adapter.",
}


class VendorInventoryAdapter(ApplicationInterface):
    """Lists excluded vendor trees. It never launches them."""

    _CAPABILITIES = (
        CapabilityDefinition("list_excluded", False, True,
                             "List vendored trees excluded from first-party manifests."),
    )

    def __init__(self, source_root: Path | None = None) -> None:
        self.source_root = (source_root or PROJECT_ROOT).resolve()

    def _entries(self) -> list[dict[str, Any]]:
        rows = []
        for name in sorted(EXCLUDED_DIRECTORY_NAMES - {".git", "__pycache__"}):
            path = self.source_root / "fermion" / name
            rows.append({
                "name": name,
                "present": path.is_dir(),
                "purpose": VENDOR_PURPOSE.get(name, "Excluded third-party material."),
                "integration_status": "excluded_not_an_adapter",
                "executable": False,
            })
        return rows

    def observe(self) -> Observation:
        return Observation(time.time(), "vendor_inventory",
                           {"excluded_count": len(self._entries()), "entries": self._entries()})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("vendor_inventory", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if action.operation != "list_excluded":
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        entries = self._entries()
        return ActionResult(action.action_id, True, False, {"entries": entries, "launched": False})

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if result.details.get("launched"):
            return VerificationResult(False, expected_effect, observed, "vendor inventory must not launch software")
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        payload = json.dumps(self.observe().state, sort_keys=True).encode("utf-8")
        return Checkpoint(uuid.uuid4().hex, self.observe().state, hashlib.sha256(payload).hexdigest(), time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
