"""Control outcomes distinguish safe refusal from attempted task failure."""

from __future__ import annotations

from enum import Enum


class ControlOutcome(str, Enum):
    SUCCESS = "success"
    TASK_FAILURE = "task_failure"
    SAFE_VETO = "safe_veto"
    APPROVAL_REQUIRED = "approval_required"
    ENVIRONMENT_UNAVAILABLE = "environment_unavailable"


def classify_control_outcome(success: bool, error: str | None = None) -> ControlOutcome:
    if success:
        return ControlOutcome.SUCCESS
    message = (error or "").lower()
    if "ownership veto" in message:
        return ControlOutcome.SAFE_VETO
    if "approval" in message:
        return ControlOutcome.APPROVAL_REQUIRED
    if "unavailable" in message or "not found" in message:
        return ControlOutcome.ENVIRONMENT_UNAVAILABLE
    return ControlOutcome.TASK_FAILURE
