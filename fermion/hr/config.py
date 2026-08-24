"""Configuration for scalable FERMiON-HR models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class HRConfig:
    modality_dims: dict[str, int] = field(default_factory=lambda: {
        "text": 32, "vision": 32, "structured": 16, "tools": 16, "history": 16,
    })
    encoded_dim: int = 32
    psi_dim: int = 16
    hidden_dim: int = 32
    memory_dim: int = 16
    validator_dim: int = 4
    candidate_dim: int = 16
    refinement_steps: int = 3
    transition_hidden_dim: int = 64
    uncertainty_members: int = 4
    seed: int = 193

    def __post_init__(self) -> None:
        if self.refinement_steps < 0:
            raise ValueError("refinement_steps cannot be negative")
        if self.encoded_dim % 2:
            raise ValueError("encoded_dim must be even for the symplectic expert")
        if not self.modality_dims or any(value <= 0 for value in self.modality_dims.values()):
            raise ValueError("modality dimensions must be positive")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RoutingWeights:
    energy: float = 1.0
    cost: float = 0.25
    uncertainty: float = 0.5
    risk: float = 2.0
    success_epsilon: float = 1e-7


@dataclass(frozen=True)
class EnergyWeights:
    state: float = 1.0
    prediction: float = 1.0
    goal: float = 1.0
    memory: float = 0.25
    uncertainty: float = 0.5
    cost: float = 0.5
    stability: float = 0.5


@dataclass(frozen=True)
class TrainingConfig:
    learning_rate: float = 2e-3
    outcome_weight: float = 1.0
    route_weight: float = 1.0
    effect_weight: float = 0.5
    energy_weight: float = 0.25
    calibration_weight: float = 0.25
    memory_weight: float = 0.1
    stability_weight: float = 0.02
    gradient_clip: float = 5.0

