"""Offline trainer; validators, never proposal models, supply outcome targets."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor
from torch.nn import functional as F

from .config import TrainingConfig
from .contracts import HRState
from .system import FermionHR


@dataclass(frozen=True)
class RoutingBatch:
    observations: dict[str, Tensor | None]
    state: HRState
    candidates: Tensor
    success_targets: Tensor
    effect_targets: Tensor
    best_indices: Tensor
    external_cost: Tensor
    external_risk: Tensor


@dataclass(frozen=True)
class TrainingMetrics:
    total: float
    outcome: float
    route: float
    effect: float
    calibration: float
    stability: float


class HRTrainer:
    def __init__(self, model: FermionHR, config: TrainingConfig | None = None):
        self.model = model
        self.config = config or TrainingConfig()
        self.optimizer = torch.optim.Adam(model.parameters(), lr=self.config.learning_rate)

    def train_step(self, batch: RoutingBatch) -> TrainingMetrics:
        self.model.train()
        decision = self.model(batch.observations, batch.state, batch.candidates,
                              batch.external_cost, batch.external_risk)
        outcome = F.binary_cross_entropy(decision.routing.success, batch.success_targets)
        route = F.cross_entropy(-decision.routing_scores, batch.best_indices)
        effect = F.mse_loss(decision.routing.effect_energy, batch.effect_targets)
        calibration = (decision.routing.success - batch.success_targets).square().mean()
        if len(decision.recursive.states) > 1:
            stability = (decision.recursive.states[-1] - decision.recursive.states[-2]).square().mean()
        else:
            stability = decision.recursive.final.new_zeros(())
        total = (self.config.outcome_weight * outcome + self.config.route_weight * route
                 + self.config.effect_weight * effect + self.config.calibration_weight * calibration
                 + self.config.stability_weight * stability)
        self.optimizer.zero_grad(); total.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.gradient_clip)
        self.optimizer.step()
        return TrainingMetrics(*(float(value.detach()) for value in
                                 (total, outcome, route, effect, calibration, stability)))

