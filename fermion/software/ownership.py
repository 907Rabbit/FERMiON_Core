"""Explicit authorization boundary for application-session control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .application import Action


class TargetOwnership(str, Enum):
    EXCLUSIVE = "exclusive"
    SHARED_AUTHORIZED = "shared_authorized"
    SHARED_UNAUTHORIZED = "shared_unauthorized"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TargetAssessment:
    ownership: TargetOwnership
    target_id: str | None
    reason: str = ""


@dataclass(frozen=True)
class OwnershipDecision:
    allowed: bool
    reason: str


class OwnershipGate:
    """Fail-closed authorization check used before a known mutating action."""

    _ALLOWED = {TargetOwnership.EXCLUSIVE, TargetOwnership.SHARED_AUTHORIZED}

    @classmethod
    def authorize(cls, action: Action, assessment: TargetAssessment, *, mutating: bool) -> OwnershipDecision:
        if not mutating or assessment.ownership in cls._ALLOWED:
            return OwnershipDecision(True, "read-only action" if not mutating else "target ownership authorized")
        return OwnershipDecision(False, f"target ownership veto: {assessment.ownership.value}; {assessment.reason}".rstrip("; "))
