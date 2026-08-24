"""Typed boundaries shared by FERMiON-HR subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import torch
from torch import Tensor


class ProgramKind(str, Enum):
    PYTHON = "python"
    POWERSHELL = "powershell"
    TOOL = "tool"
    GUI = "gui"
    UNREAL_PYTHON = "unreal_python"


@dataclass(frozen=True)
class CandidateProgram:
    candidate_id: str
    source: str
    kind: ProgramKind = ProgramKind.PYTHON
    features: tuple[float, ...] = ()
    declared_artifacts: tuple[str, ...] = ()
    estimated_cost: float = 0.0
    estimated_risk: float = 0.0
    reversible: bool = True
    provenance: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidatorEvidence:
    success: float
    information: float
    goal_score: float = 0.0
    contradiction: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def tensor(self, *, dtype: torch.dtype = torch.float32, device: torch.device | None = None) -> Tensor:
        return torch.tensor([self.success, self.information, self.goal_score, self.contradiction],
                            dtype=dtype, device=device)


@dataclass(frozen=True)
class RouteScore:
    candidate_id: str
    success_probability: float
    predicted_energy: float
    cost: float
    uncertainty: float
    risk: float
    total: float


@dataclass
class HRState:
    psi: Tensor
    memory: Tensor

    def detached(self) -> "HRState":
        return HRState(self.psi.detach().clone(), self.memory.detach().clone())


@dataclass(frozen=True)
class ExecutionResult:
    candidate_id: str
    return_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    changed_artifacts: tuple[str, ...]
    undeclared_artifacts: tuple[str, ...]
    committed: bool
    recovered: bool
    validator: ValidatorEvidence


@dataclass(frozen=True)
class DecisionTrace:
    selected_id: str
    scores: tuple[RouteScore, ...]
    energy_terms: dict[str, float]
    refinement_deltas: tuple[float, ...]

