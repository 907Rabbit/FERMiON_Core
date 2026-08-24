"""Seven-term diagnostic energy used for decisions and post-hoc analysis."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from .config import EnergyWeights, HRConfig
from .recursive_core import RecursiveTrace
from .uncertainty import bernoulli_entropy


@dataclass(frozen=True)
class EnergyTerms:
    state: Tensor
    prediction: Tensor
    goal: Tensor
    memory: Tensor
    uncertainty: Tensor
    cost: Tensor
    stability: Tensor
    total: Tensor

    def named(self) -> dict[str, Tensor]:
        return {name: getattr(self, name) for name in (
            "state", "prediction", "goal", "memory", "uncertainty", "cost", "stability", "total"
        )}


class SevenTermEnergy(nn.Module):
    def __init__(self, config: HRConfig, weights: EnergyWeights | None = None):
        super().__init__()
        self.weights = weights or EnergyWeights()
        self.state_reference = nn.Linear(config.psi_dim + config.memory_dim + config.encoded_dim,
                                         config.hidden_dim)
        self.memory_projection = nn.Linear(config.memory_dim, config.psi_dim)

    def forward(self, trace: RecursiveTrace, psi: Tensor, memory: Tensor, encoded: Tensor,
                success_probability: Tensor, predicted_effect: Tensor,
                observed_effect: Tensor | None, effect_variance: Tensor,
                cost: Tensor, contradiction: Tensor | None = None,
                ood_score: Tensor | None = None) -> EnergyTerms:
        reference = torch.tanh(self.state_reference(torch.cat((psi, memory, encoded), dim=-1)))
        state = (trace.final - reference).square().mean(dim=-1)
        prediction = (predicted_effect - observed_effect).square().mean(dim=-1) if observed_effect is not None else effect_variance.mean(dim=-1)
        goal = 1.0 - success_probability
        memory_term = (psi - self.memory_projection(memory)).square().mean(dim=-1)
        uncertainty = effect_variance.sum(dim=-1) + bernoulli_entropy(success_probability)
        if len(trace.states) > 1:
            deltas = [torch.linalg.vector_norm(right - left, dim=-1)
                      for left, right in zip(trace.states, trace.states[1:])]
            stability = deltas[-1]
            for previous, current in zip(deltas, deltas[1:]):
                stability = stability + torch.relu(current - previous)
        else:
            stability = torch.linalg.vector_norm(trace.final, dim=-1)
        stability = stability + (contradiction if contradiction is not None else 0.0)
        stability = stability + (ood_score if ood_score is not None else 0.0)
        total = (self.weights.state * state + self.weights.prediction * prediction
                 + self.weights.goal * goal + self.weights.memory * memory_term
                 + self.weights.uncertainty * uncertainty + self.weights.cost * cost
                 + self.weights.stability * stability)
        return EnergyTerms(state, prediction, goal, memory_term, uncertainty, cost, stability, total)

