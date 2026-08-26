"""Named control-plane surfaces for vendored trees. Live attack/scan/agent launch is refused."""

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

LIVE_REFUSAL = (
    "LIVE_EXECUTION_REFUSED: FERMiON will not launch this vendored tool, open a shell to it, "
    "or perform network attacks, people-tracking, exploit/phishing payloads, or unconstrained coding-agent runs."
)


class VendoredSurfaceAdapter(ApplicationInterface):
    """Inspect a vendored tree. Optional catalog listing. No subprocess."""

    def __init__(self, name: str, relative_tree: str, *, catalog_glob: str | None = None,
                 source_root: Path | None = None) -> None:
        self.name = name
        self.source_root = (source_root or PROJECT_ROOT).resolve()
        self.tree = self.source_root / relative_tree
        self.catalog_glob = catalog_glob
        self._capabilities = (
            CapabilityDefinition("status", False, True, "Report tree presence without launching the tool."),
            CapabilityDefinition("list_catalog", False, True, "List static catalog names from the tree."),
        )

    def _catalog(self) -> list[str]:
        if not self.catalog_glob or not self.tree.is_dir():
            return []
        return sorted(path.name for path in self.tree.glob(self.catalog_glob) if path.is_file())[:200]

    def observe(self) -> Observation:
        return Observation(time.time(), self.name, {
            "tree_present": self.tree.is_dir(),
            "live_execution": False,
            "refusal": LIVE_REFUSAL if self.tree.is_dir() else "tree_absent",
        })

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(self.name, self._capabilities)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        if action.operation == "status":
            return ActionResult(action.action_id, True, False, self.observe().state)
        if action.operation == "list_catalog":
            names = self._catalog()
            return ActionResult(action.action_id, True, False, {
                "names": names, "count": len(names), "launched": False, "live_execution": False,
            })
        return ActionResult(action.action_id, False, False, error=LIVE_REFUSAL)

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if result.details.get("launched") or result.details.get("live_execution"):
            return VerificationResult(False, expected_effect, observed, LIVE_REFUSAL)
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        state = self.observe().state
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)


def bettercap_adapter(source_root: Path | None = None) -> VendoredSurfaceAdapter:
    return VendoredSurfaceAdapter("bettercap", "fermion/bettercap", catalog_glob="modules/**/*.go",
                                  source_root=source_root)


def hackingtool_adapter(source_root: Path | None = None) -> VendoredSurfaceAdapter:
    return VendoredSurfaceAdapter("hackingtool", "fermion/hackingtool",
                                  catalog_glob="src/hackingtool/catalog/*.yaml", source_root=source_root)


def ghosttrack_adapter(source_root: Path | None = None) -> VendoredSurfaceAdapter:
    return VendoredSurfaceAdapter("ghosttrack", "fermion/GhostTrack", source_root=source_root)


def spiderfoot_adapter(source_root: Path | None = None) -> VendoredSurfaceAdapter:
    return VendoredSurfaceAdapter("spiderfoot", "fermion/spiderfoot", catalog_glob="modules/sfp_*.py",
                                  source_root=source_root)


def codex_adapter(source_root: Path | None = None) -> VendoredSurfaceAdapter:
    return VendoredSurfaceAdapter("codex", "fermion/codex", source_root=source_root)
