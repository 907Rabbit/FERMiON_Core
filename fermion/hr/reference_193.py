"""Canonical 193-parameter FERMiON-HR regression specimen.

Do not change dimensions, parameter registration order, activation functions, or
the three shared refinement passes without changing ``FORMAT_VERSION``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import torch
from torch import Tensor, nn
from torch.nn import functional as F

FORMAT_VERSION = 1
REFERENCE_SEED = 193
PARAMETER_ORDER = (
    "W_e", "b_e", "W_0", "b_0", "W_r", "b_r", "w_g", "b_g",
    "W_psi", "b_psi", "w_eta", "b_eta", "W_o", "b_o",
)


@dataclass(frozen=True)
class ReferenceConfig:
    eps: float = 1e-7
    memory_rho_min: float = 0.02
    memory_rho_validator: float = 0.48
    memory_rho_novelty: float = 0.25
    energy_weights: tuple[float, ...] = (1.0, 1.0, 1.0, 0.25, 0.5, 1.0, 0.5)


class ForwardTrace(NamedTuple):
    encoded: Tensor
    hidden: tuple[Tensor, Tensor, Tensor, Tensor]
    gates: tuple[Tensor, Tensor, Tensor]
    logits: Tensor
    success: Tensor
    effect_energy: Tensor


class EnergyReport(NamedTuple):
    refine: Tensor
    goal: Tensor
    prediction: Tensor
    memory: Tensor
    uncertainty: Tensor
    cost: Tensor
    stability: Tensor
    total: Tensor


def _parameter(shape: tuple[int, ...]) -> nn.Parameter:
    return nn.Parameter(torch.empty(shape, dtype=torch.float64))


class FermionHR193(nn.Module):
    """Exact reference network, using float64 for stable regression checks."""

    def __init__(self, config: ReferenceConfig | None = None, seed: int = REFERENCE_SEED):
        super().__init__()
        self.config = config or ReferenceConfig()
        # Registration order is part of the checkpoint contract.
        self.W_e, self.b_e = _parameter((4, 4)), _parameter((4,))
        self.W_0, self.b_0 = _parameter((4, 10)), _parameter((4,))
        self.W_r, self.b_r = _parameter((4, 14)), _parameter((4,))
        self.w_g, self.b_g = _parameter((1, 14)), _parameter((1,))
        self.W_psi, self.b_psi = _parameter((3, 10)), _parameter((3,))
        self.w_eta, self.b_eta = _parameter((1, 10)), _parameter((1,))
        self.W_o, self.b_o = _parameter((2, 4)), _parameter((2,))
        self.reset_parameters(seed)

    def reset_parameters(self, seed: int = REFERENCE_SEED) -> None:
        generator = torch.Generator(device="cpu").manual_seed(seed)
        with torch.no_grad():
            for parameter in self.parameters():
                parameter.uniform_(-0.2, 0.2, generator=generator)

    @property
    def parameter_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(self, x: Tensor, psi: Tensor, memory: Tensor, steps: int = 3) -> ForwardTrace:
        if steps < 0:
            raise ValueError("steps must be non-negative")
        e = torch.tanh(F.linear(x, self.W_e, self.b_e))
        h = torch.tanh(F.linear(torch.cat((e, psi, memory), dim=-1), self.W_0, self.b_0))
        hidden: list[Tensor] = [h]
        gates: list[Tensor] = []
        for _ in range(steps):
            joined = torch.cat((h, psi, memory, e), dim=-1)
            candidate = torch.tanh(F.linear(joined, self.W_r, self.b_r))
            gate = torch.sigmoid(F.linear(joined, self.w_g, self.b_g))
            h = (1.0 - gate) * h + gate * candidate
            hidden.append(h)
            gates.append(gate)
        logits = F.linear(h, self.W_o, self.b_o)
        # The canonical trace has four states. Ablation traces pad by repeating the
        # final state; their output remains useful without altering parameter layout.
        hidden.extend([h] * (4 - len(hidden)))
        gates.extend([torch.zeros_like(logits[..., :1])] * (3 - len(gates)))
        return ForwardTrace(e, tuple(hidden[:4]), tuple(gates[:3]), logits,
                            torch.sigmoid(logits[..., 0]), F.softplus(logits[..., 1]))

    def update_from_state(self, psi: Tensor, trace: ForwardTrace, e_next: Tensor,
                          validator: Tensor, memory: Tensor, novelty: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        if validator.shape[-1] != 2:
            raise ValueError("validator must contain [success, information]")
        u = torch.cat((trace.hidden[3], e_next, validator), dim=-1)
        candidate = torch.tanh(F.linear(u, self.W_psi, self.b_psi))
        eta = torch.sigmoid(F.linear(u, self.w_eta, self.b_eta)) * validator[..., 1:2].clamp(0, 1)
        psi_next = (1.0 - eta) * psi + eta * candidate
        q = torch.stack((validator[..., 0], 1.0 - validator[..., 0], novelty), dim=-1)
        rho = (self.config.memory_rho_min + self.config.memory_rho_validator * validator[..., 1]
               + self.config.memory_rho_novelty * novelty).clamp(0, 1).unsqueeze(-1)
        rho = rho * validator[..., 1:2].clamp(0, 1)
        return psi_next, (1.0 - rho) * memory + rho * q, eta

    def energy(self, trace: ForwardTrace, psi_next: Tensor, memory_next: Tensor,
               validator_success: Tensor, cost: Tensor) -> EnergyReport:
        h0, h1, h2, h3 = trace.hidden
        refine = torch.linalg.vector_norm(h3 - h2, dim=-1)
        goal = 1.0 - trace.success
        prediction = (trace.success - validator_success).square()
        memory_term = torch.linalg.vector_norm(psi_next - memory_next, dim=-1)
        p = trace.success.clamp(self.config.eps, 1.0 - self.config.eps)
        uncertainty = -p * torch.log(p) - (1.0 - p) * torch.log(1.0 - p)
        differences = [torch.linalg.vector_norm(h1 - h0, dim=-1),
                       torch.linalg.vector_norm(h2 - h1, dim=-1),
                       torch.linalg.vector_norm(h3 - h2, dim=-1)]
        previous = torch.linalg.vector_norm(h0, dim=-1)
        stability = torch.zeros_like(previous)
        for difference in differences:
            stability = stability + F.relu(difference - previous)
            previous = difference
        terms = (refine, goal, prediction, memory_term, uncertainty, cost, stability)
        total = sum(weight * term for weight, term in zip(self.config.energy_weights, terms))
        return EnergyReport(*terms, total)

    def save_checkpoint(self, path: str | Path, psi: Tensor, memory: Tensor) -> None:
        torch.save({"format": FORMAT_VERSION, "parameter_order": PARAMETER_ORDER,
                    "state_dict": self.state_dict(), "psi": psi, "memory": memory}, path)

    @classmethod
    def load_checkpoint(cls, path: str | Path) -> tuple["FermionHR193", Tensor, Tensor]:
        data = torch.load(path, map_location="cpu", weights_only=True)
        if data.get("format") != FORMAT_VERSION or tuple(data.get("parameter_order", ())) != PARAMETER_ORDER:
            raise ValueError("incompatible FERMiON-HR checkpoint")
        model = cls()
        model.load_state_dict(data["state_dict"], strict=True)
        return model, data["psi"], data["memory"]


def reference_inputs() -> tuple[Tensor, Tensor, Tensor]:
    return (torch.tensor([[0.25, -0.50, 0.75, 0.10]], dtype=torch.float64),
            torch.tensor([[0.10, -0.20, 0.30]], dtype=torch.float64),
            torch.tensor([[0.40, 0.20, 0.05]], dtype=torch.float64))
