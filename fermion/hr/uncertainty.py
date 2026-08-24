"""Epistemic and routing uncertainty estimators."""

from __future__ import annotations

import torch
from torch import Tensor, nn


class EffectEnsemble(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, members: int = 4, hidden_dim: int = 64):
        super().__init__()
        if members < 2:
            raise ValueError("uncertainty ensembles require at least two members")
        self.members = nn.ModuleList(
            nn.Sequential(nn.Linear(input_dim, hidden_dim), nn.Tanh(), nn.Linear(hidden_dim, output_dim))
            for _ in range(members)
        )

    def forward(self, value: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        predictions = torch.stack([member(value) for member in self.members], dim=0)
        mean = predictions.mean(dim=0)
        variance = predictions.var(dim=0, unbiased=False)
        return mean, variance, predictions


def bernoulli_entropy(probability: Tensor, epsilon: float = 1e-7) -> Tensor:
    probability = probability.clamp(epsilon, 1.0 - epsilon)
    return -probability * torch.log(probability) - (1.0 - probability) * torch.log(1.0 - probability)


def routing_entropy(probabilities: Tensor, epsilon: float = 1e-7) -> Tensor:
    normalized = probabilities / probabilities.sum(dim=-1, keepdim=True).clamp_min(epsilon)
    return -(normalized * torch.log(normalized.clamp_min(epsilon))).sum(dim=-1)

