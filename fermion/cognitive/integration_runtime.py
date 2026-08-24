"""Narrow composition root for FERMiON perception, planning, action, and evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fermion.control_plane import ApplicationControlPlane, ControlPlan, ExecutionReport, PlanValidation

from .integration_registry import FirstPartyManifest, ProvenanceRecord, ProvenanceRegistry, canonical_json, sha256_bytes
from .workspace import GlobalWorkspace, WorkspaceBroadcast


@dataclass(frozen=True)
class PerceptionEvent:
    source: str
    content: str

    def digest(self) -> str:
        return sha256_bytes(canonical_json(asdict(self)))


@dataclass(frozen=True)
class RuntimePlan:
    perception: PerceptionEvent
    workspace: WorkspaceBroadcast
    plan: ControlPlan
    validation: PlanValidation
    plan_sha256: str


@dataclass(frozen=True)
class RuntimeReceipt:
    runtime_plan: RuntimePlan
    report: ExecutionReport
    provenance: ProvenanceRecord


class FermionRuntime:
    """Compose existing boundaries without granting a planner any new authority."""

    def __init__(self, *, control_plane: ApplicationControlPlane, registry: ProvenanceRegistry,
                 source_root: Path, source_manifest: FirstPartyManifest) -> None:
        if not source_manifest.verify(source_root):
            raise ValueError("first-party source manifest verification failed")
        self.control_plane = control_plane
        self.registry = registry
        self.source_manifest_sha256 = source_manifest.manifest_sha256
        self.workspace = GlobalWorkspace()

    def plan(self, event: PerceptionEvent, planner_response: str) -> RuntimePlan:
        """Parse and validate a declared plan; never execute it at planning time."""
        selected = self.workspace.broadcast({event.source: 1.0})
        control_plan = self.control_plane.parse_plan(event.content, planner_response)
        validation = self.control_plane.validate(control_plan)
        return RuntimePlan(event, selected, control_plan, validation, sha256_bytes(canonical_json({
            "user_request": control_plan.user_request, "summary": control_plan.summary,
            "actions": [asdict(action) for action in control_plan.actions],
            "requires_approval": control_plan.requires_approval,
        })))

    def authorize(self, runtime_plan: RuntimePlan, *, approved: bool) -> RuntimeReceipt:
        """Delegate all action semantics to the control plane and record the observed outcome."""
        report = self.control_plane.execute(runtime_plan.plan, approved=approved)
        if report.rolled_back:
            state = "action_rolled_back"
        elif report.validation.valid and report.records:
            state = "action_completed"
        elif "approval" in " ".join(report.validation.reasons).lower():
            state = "approval_required"
        else:
            state = "action_rejected"
        provenance = self.registry.append(
            track="authorized_action", state=state, source_manifest_sha256=self.source_manifest_sha256,
            inputs={"perception_sha256": runtime_plan.perception.digest(), "plan_sha256": runtime_plan.plan_sha256},
            authority="user-approved" if approved else "approval-not-granted",
        )
        return RuntimeReceipt(runtime_plan, report, provenance)
