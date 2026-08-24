"""Shared-weight recursive inference for production FERMiON-HR."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from .config import HRConfig


@dataclass(frozen=True)
class RecursiveTrace:
    states: tuple[Tensor, ...]
    gates: tuple[Tensor, ...]

    @property
    def final(self) -> Tensor:
        return self.states[-1]


class RecursiveCore(nn.Module):
    def __init__(self, config: HRConfig):
        super().__init__()
        self.config = config
        context_dim = config.psi_dim + config.memory_dim + config.encoded_dim
        joined_dim = config.hidden_dim + context_dim
        self.initializer = nn.Linear(context_dim, config.hidden_dim)
        self.candidate = nn.Linear(joined_dim, config.hidden_dim)
        self.gate = nn.Linear(joined_dim, config.hidden_dim)

    def forward(self, psi: Tensor, memory: Tensor, encoded: Tensor,
                steps: int | None = None) -> RecursiveTrace:
        count = self.config.refinement_steps if steps is None else steps
        if count < 0:
            raise ValueError("steps cannot be negative")
        context = torch.cat((psi, memory, encoded), dim=-1)
        hidden = torch.tanh(self.initializer(context))
        states, gates = [hidden], []
        for _ in range(count):
            joined = torch.cat((hidden, context), dim=-1)
            candidate = torch.tanh(self.candidate(joined))
            gate = torch.sigmoid(self.gate(joined))
            hidden = (1.0 - gate) * hidden + gate * candidate
            states.append(hidden)
            gates.append(gate)
        return RecursiveTrace(tuple(states), tuple(gates))
