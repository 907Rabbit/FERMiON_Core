"""Integrated FERMiON-HR controller."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor, nn

from .config import EnergyWeights, HRConfig, RoutingWeights
from .contracts import CandidateProgram, DecisionTrace, HRState, RouteScore, ValidatorEvidence
from .encoders import MultimodalEncoder
from .energy import EnergyTerms, SevenTermEnergy
from .recursive_core import RecursiveCore, RecursiveTrace
from .routing import RoutingHead, RoutingPrediction
from .transition import HybridTransition


@dataclass(frozen=True)
class ControllerDecision:
    selected_index: Tensor
    encoded: Tensor
    recursive: RecursiveTrace
    routing: RoutingPrediction
    routing_scores: Tensor
    predicted_next: Tensor
    effect_variance: Tensor
    energy: EnergyTerms
    trace: DecisionTrace | None


class FermionHR(nn.Module):
    def __init__(self, config: HRConfig | None = None,
                 routing_weights: RoutingWeights | None = None,
                 energy_weights: EnergyWeights | None = None):
        super().__init__()
        self.config = config or HRConfig()
        torch.manual_seed(self.config.seed)
        self.encoder = MultimodalEncoder(self.config)
        self.core = RecursiveCore(self.config)
        self.router = RoutingHead(self.config, routing_weights)
        self.transition = HybridTransition(self.config)
        self.energy_model = SevenTermEnergy(self.config, energy_weights)
        update_input = self.config.hidden_dim + self.config.encoded_dim + self.config.validator_dim
        self.psi_candidate = nn.Linear(update_input, self.config.psi_dim)
        self.psi_gate = nn.Linear(update_input, self.config.psi_dim)
        self.memory_candidate = nn.Linear(update_input, self.config.memory_dim)
        self.memory_gate = nn.Linear(update_input, self.config.memory_dim)

    def initial_state(self, batch_size: int = 1, *, dtype: torch.dtype = torch.float32,
                      device: torch.device | None = None) -> HRState:
        return HRState(torch.zeros(batch_size, self.config.psi_dim, dtype=dtype, device=device),
                       torch.zeros(batch_size, self.config.memory_dim, dtype=dtype, device=device))

    def candidate_features(self, candidates: list[CandidateProgram], *, dtype: torch.dtype = torch.float32,
                           device: torch.device | None = None) -> Tensor:
        rows = []
        for candidate in candidates:
            base = list(candidate.features[:self.config.candidate_dim])
            derived = [candidate.estimated_cost, candidate.estimated_risk, float(candidate.reversible),
                       min(len(candidate.source) / 10000.0, 1.0)]
            base.extend(derived[:max(0, self.config.candidate_dim - len(base))])
            base.extend([0.0] * (self.config.candidate_dim - len(base)))
            rows.append(base[:self.config.candidate_dim])
        if not rows:
            raise ValueError("at least one candidate is required")
        return torch.tensor([rows], dtype=dtype, device=device)

    def forward(self, observations: dict[str, Tensor | None], state: HRState,
                candidates: Tensor, external_cost: Tensor | None = None,
                external_risk: Tensor | None = None, observed_effect: Tensor | None = None,
                candidate_contracts: list[CandidateProgram] | None = None) -> ControllerDecision:
        encoded, _ = self.encoder(observations)
        recursive = self.core(state.psi, state.memory, encoded)
        routing = self.router(recursive.final, state.psi, state.memory, encoded, candidates)
        selected, scores = self.router.select(routing, external_cost, external_risk)
        gather_candidate = selected[..., None, None].expand(*selected.shape, 1, candidates.shape[-1])
        chosen_candidate = candidates.gather(-2, gather_candidate).squeeze(-2)
        predicted_next, effect_variance, _ = self.transition(encoded, recursive.final, chosen_candidate)
        gather_scalar = selected.unsqueeze(-1)
        success = routing.success.gather(-1, gather_scalar).squeeze(-1)
        selected_cost = (routing.learned_cost if external_cost is None else external_cost).gather(-1, gather_scalar).squeeze(-1)
        energy = self.energy_model(recursive, state.psi, state.memory, encoded, success,
                                   predicted_next, observed_effect, effect_variance, selected_cost)
        diagnostic = self._decision_trace(selected, scores, routing, energy, recursive,
                                          candidate_contracts) if selected.numel() == 1 else None
        return ControllerDecision(selected, encoded, recursive, routing, scores, predicted_next,
                                  effect_variance, energy, diagnostic)

    def update_state(self, state: HRState, decision: ControllerDecision,
                     next_observations: dict[str, Tensor | None], evidence: ValidatorEvidence) -> HRState:
        encoded_next, _ = self.encoder(next_observations)
        validator = evidence.tensor(dtype=encoded_next.dtype, device=encoded_next.device)
        validator = validator.expand(encoded_next.shape[0], -1)
        joined = torch.cat((decision.recursive.final, encoded_next, validator), dim=-1)
        reliability = validator[..., 1:2].clamp(0.0, 1.0)
        psi_gate = torch.sigmoid(self.psi_gate(joined)) * reliability
        memory_gate = torch.sigmoid(self.memory_gate(joined)) * reliability
        psi = (1.0 - psi_gate) * state.psi + psi_gate * torch.tanh(self.psi_candidate(joined))
        memory = ((1.0 - memory_gate) * state.memory
                  + memory_gate * torch.tanh(self.memory_candidate(joined)))
        return HRState(psi, memory)

    @staticmethod
    def _decision_trace(selected: Tensor, scores: Tensor, prediction: RoutingPrediction,
                        energy: EnergyTerms, recursive: RecursiveTrace,
                        candidates: list[CandidateProgram] | None) -> DecisionTrace:
        ids = ([candidate.candidate_id for candidate in candidates]
               if candidates else [str(index) for index in range(scores.shape[-1])])
        route_scores = tuple(RouteScore(
            ids[index], float(prediction.success[0, index].detach()),
            float(prediction.effect_energy[0, index].detach()),
            float(prediction.learned_cost[0, index].detach()),
            float(prediction.uncertainty[0, index].detach()),
            float(prediction.risk[0, index].detach()), float(scores[0, index].detach()))
            for index in range(scores.shape[-1]))
        energy_values = {name: float(value.reshape(-1)[0].detach())
                         for name, value in energy.named().items()}
        deltas = tuple(float(torch.linalg.vector_norm(right - left).detach())
                       for left, right in zip(recursive.states, recursive.states[1:]))
        return DecisionTrace(ids[int(selected.item())], route_scores, energy_values, deltas)

