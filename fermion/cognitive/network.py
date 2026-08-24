"""Trainable recurrent FERMiON cognitive state and explicit (F, K) dynamics."""
from __future__ import annotations

from dataclasses import dataclass
import torch
from torch import Tensor, nn


@dataclass
class FermionState:
    psi: Tensor; phi: Tensor; memory_state: Tensor; attention_state: Tensor; prediction_state: Tensor
    novelty_state: Tensor; self_state: Tensor; goal_state: Tensor; confidence_state: Tensor; affect_state: Tensor; time_state: Tensor
    def detached(self) -> "FermionState": return FermionState(*[value.detach().clone() for value in self.__dict__.values()])


class FermionNetwork(nn.Module):
    def __init__(self, input_dim: int = 96, latent_dim: int = 128, self_dim: int = 64, goal_dim: int = 64):
        super().__init__(); self.input_dim, self.latent_dim = input_dim, latent_dim
        self.encoder = nn.Sequential(nn.Linear(input_dim, latent_dim), nn.Tanh(), nn.Linear(latent_dim, latent_dim))
        self.recurrent = nn.GRUCell(latent_dim * 2, latent_dim)
        self.predictor, self.workspace_gate = nn.Linear(latent_dim, latent_dim), nn.Linear(latent_dim * 2, latent_dim)
        self.self_model, self.goal_model = nn.Linear(latent_dim * 2, self_dim), nn.Linear(latent_dim * 2, goal_dim)
        self.confidence = nn.Linear(latent_dim, 1)

    def initial_state(self, device: torch.device | None = None) -> FermionState:
        z = lambda d: torch.zeros(1, d, device=device)
        return FermionState(z(self.latent_dim),z(self.latent_dim),z(self.latent_dim),z(self.latent_dim),z(self.latent_dim),z(1),z(self.self_model.out_features),z(self.goal_model.out_features),z(1),z(1),z(1))

    def refine(self, observation: Tensor, state: FermionState, iterations: int = 3) -> tuple[FermionState, dict[str, Tensor]]:
        encoded = torch.tanh(self.encoder(observation)); psi, memory = state.psi, state.memory_state
        for _ in range(iterations):
            gate = torch.sigmoid(self.workspace_gate(torch.cat((encoded, psi), -1)))
            psi = self.recurrent(torch.cat((encoded, gate * memory), -1), psi)
            memory = .88 * memory + .12 * psi
        prediction = self.predictor(psi); novelty = (prediction - encoded).square().mean(-1, keepdim=True)
        self_state = torch.tanh(self.self_model(torch.cat((psi, state.self_state.new_zeros(1, self.latent_dim)), -1)))
        goal_state = torch.tanh(self.goal_model(torch.cat((psi, encoded), -1)))
        confidence = torch.sigmoid(self.confidence(psi) - novelty)
        next_state = FermionState(psi, encoded, memory, gate, prediction, novelty, self_state, goal_state, confidence, state.affect_state, state.time_state + 1)
        terms = {"prediction": novelty, "memory": (psi-memory).square().mean(-1,keepdim=True), "coherence": (psi-encoded).square().mean(-1,keepdim=True), "novelty": -novelty, "integration": gate.var(-1,keepdim=True), "goal": goal_state.square().mean(-1,keepdim=True), "complexity": psi.square().mean(-1,keepdim=True), "self_model": self_state.square().mean(-1,keepdim=True)}
        terms["total"] = sum(terms.values()); return next_state, terms
