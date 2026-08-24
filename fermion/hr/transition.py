"""Hybrid discrete/continuous predictive transition model."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from fermion_symplectic_dysib import SymplecticTransition

from .config import HRConfig
from .uncertainty import EffectEnsemble


class HybridTransition(nn.Module):
    """Mixture of a discrete residual expert and a symplectic continuous expert."""

    def __init__(self, config: HRConfig):
        super().__init__()
        dimension = config.encoded_dim
        self.discrete = nn.Sequential(nn.Linear(dimension, config.transition_hidden_dim), nn.Tanh(),
                                      nn.Linear(config.transition_hidden_dim, dimension))
        self.continuous = SymplecticTransition(dimension, blocks=3,
                                               hidden_dim=config.transition_hidden_dim // 2)
        self.mode = nn.Linear(config.hidden_dim + config.candidate_dim, 2)
        self.effect = EffectEnsemble(config.hidden_dim + config.candidate_dim, dimension,
                                     config.uncertainty_members, config.transition_hidden_dim)

    def forward(self, encoded: Tensor, hidden: Tensor, candidate: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        context = torch.cat((hidden, candidate), dim=-1)
        weights = torch.softmax(self.mode(context), dim=-1)
        discrete = encoded + self.discrete(encoded)
        continuous = self.continuous(encoded)
        prediction = weights[..., :1] * discrete + weights[..., 1:] * continuous
        effect_mean, effect_variance, _ = self.effect(context)
        return prediction + effect_mean, effect_variance, weights

