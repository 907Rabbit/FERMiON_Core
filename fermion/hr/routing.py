"""Candidate scoring and evidence-grounded route selection."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from .config import HRConfig, RoutingWeights


@dataclass(frozen=True)
class RoutingPrediction:
    success: Tensor
    effect_energy: Tensor
    uncertainty: Tensor
    risk: Tensor
    learned_cost: Tensor


class RoutingHead(nn.Module):
    def __init__(self, config: HRConfig, weights: RoutingWeights | None = None):
        super().__init__()
        self.weights = weights or RoutingWeights()
        input_dim = config.hidden_dim + config.psi_dim + config.memory_dim + config.encoded_dim + config.candidate_dim
        self.network = nn.Sequential(nn.Linear(input_dim, config.transition_hidden_dim), nn.Tanh(),
                                     nn.Linear(config.transition_hidden_dim, 5))

    def forward(self, hidden: Tensor, psi: Tensor, memory: Tensor, encoded: Tensor,
                candidates: Tensor) -> RoutingPrediction:
        # State tensors are [batch, dim], candidates are [batch, candidates, dim].
        count = candidates.shape[-2]
        expand = lambda value: value.unsqueeze(-2).expand(*value.shape[:-1], count, value.shape[-1])
        joined = torch.cat((expand(hidden), expand(psi), expand(memory), expand(encoded), candidates), dim=-1)
        raw = self.network(joined)
        return RoutingPrediction(torch.sigmoid(raw[..., 0]), F.softplus(raw[..., 1]),
                                 F.softplus(raw[..., 2]), torch.sigmoid(raw[..., 3]),
                                 F.softplus(raw[..., 4]))

    def scores(self, prediction: RoutingPrediction, external_cost: Tensor | None = None,
               external_risk: Tensor | None = None) -> Tensor:
        cost = prediction.learned_cost if external_cost is None else external_cost
        risk = prediction.risk if external_risk is None else torch.maximum(prediction.risk, external_risk)
        return (-torch.log(prediction.success + self.weights.success_epsilon)
                + self.weights.energy * prediction.effect_energy
                + self.weights.cost * cost + self.weights.uncertainty * prediction.uncertainty
                + self.weights.risk * risk)

    def select(self, prediction: RoutingPrediction, external_cost: Tensor | None = None,
               external_risk: Tensor | None = None) -> tuple[Tensor, Tensor]:
        scores = self.scores(prediction, external_cost, external_risk)
        return scores.argmin(dim=-1), scores

