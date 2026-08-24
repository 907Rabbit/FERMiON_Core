"""Small multimodal AI-G1 core, baselines, and replay memory."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Mapping

import torch
from torch import Tensor, nn
from torch.nn import functional as F

from .spectral import LearnableSpectralField, SpectralFieldOutput


class ReplayBuffer:
    """Bounded CPU replay store; tensors are copied to prevent aliasing updates."""

    def __init__(self, capacity: int = 1024) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._items: deque[dict[str, Tensor]] = deque(maxlen=capacity)

    def append(self, **tensors: Tensor) -> None:
        if not tensors:
            raise ValueError("a replay item needs tensors")
        self._items.append({name: value.detach().cpu().clone() for name, value in tensors.items()})

    def sample(self, count: int, *, generator: torch.Generator | None = None) -> dict[str, Tensor]:
        if not self._items:
            raise ValueError("cannot sample an empty replay buffer")
        count = min(count, len(self._items))
        order = torch.randperm(len(self._items), generator=generator)[:count].tolist()
        keys = self._items[0].keys()
        return {key: torch.stack([self._items[index][key] for index in order]) for key in keys}

    def __len__(self) -> int:
        return len(self._items)


class MLPBaseline(nn.Module):
    """Matched non-spectral baseline for AI-G1 falsification experiments."""

    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(input_dim, hidden_dim), nn.GELU(), nn.Linear(hidden_dim, output_dim))

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


class TransformerBaseline(nn.Module):
    """Matched transformer baseline for tokenised AI-G1 inputs."""

    def __init__(self, token_dim: int, output_dim: int, *, heads: int = 2, layers: int = 1) -> None:
        super().__init__()
        block = nn.TransformerEncoderLayer(token_dim, heads, dim_feedforward=token_dim * 2,
                                           batch_first=True, dropout=0.0, activation="gelu")
        self.encoder = nn.TransformerEncoder(block, layers)
        self.head = nn.Linear(token_dim, output_dim)

    def forward(self, tokens: Tensor) -> Tensor:
        return self.head(self.encoder(tokens).mean(dim=1))


@dataclass(frozen=True)
class GeneralistOutput:
    classification: Tensor
    regression: Tensor
    time_series: Tensor
    reconstruction: Tensor
    uncertainty: Tensor
    spectral: SpectralFieldOutput
    workspace: Tensor


class MultimodalSpectralGeneralist(nn.Module):
    """One shared spectral/workspace core with four task-specific output heads."""

    def __init__(self, modality_dims: Mapping[str, int], *, token_dim: int = 24,
                 modes: int = 8, classes: int = 2, horizon: int = 3,
                 reconstruction_dim: int | None = None,
                 use_spectral_field: bool = True) -> None:
        super().__init__()
        if not modality_dims:
            raise ValueError("at least one modality is required")
        self.modality_dims = dict(modality_dims)
        self.modality_order = tuple(modality_dims)
        self.token_dim, self.modes, self.use_spectral_field = token_dim, modes, use_spectral_field
        self.adapters = nn.ModuleDict({name: nn.Linear(dim, token_dim) for name, dim in modality_dims.items()})
        self.to_spectral = nn.Linear(token_dim, modes)
        self.field = LearnableSpectralField()
        layer = nn.TransformerEncoderLayer(token_dim, nhead=2, dim_feedforward=token_dim * 2,
                                           batch_first=True, dropout=0.0, activation="gelu")
        self.workspace = nn.TransformerEncoder(layer, num_layers=1)
        self.classification_head = nn.Linear(token_dim, classes)
        self.regression_head = nn.Linear(token_dim, 1)
        self.time_series_head = nn.Linear(token_dim, horizon)
        self.reconstruction_head = nn.Linear(token_dim, reconstruction_dim or max(modality_dims.values()))
        self.uncertainty_head = nn.Linear(token_dim, 1)
        self.register_buffer("in_distribution_center", torch.zeros(token_dim))
        self.register_buffer("raw_input_center", torch.zeros(sum(modality_dims.values())))

    def set_in_distribution_reference(self, modalities: Mapping[str, Tensor]) -> None:
        with torch.no_grad():
            self.in_distribution_center.copy_(self._tokens(modalities).mean(dim=(0, 1)))
            self.raw_input_center.copy_(self._raw_features(modalities).mean(dim=0))

    def _raw_features(self, modalities: Mapping[str, Tensor]) -> Tensor:
        present = [value for name in self.modality_order if (value := modalities.get(name)) is not None]
        if not present:
            raise ValueError("at least one declared modality must be supplied")
        batch = present[0].shape[0]
        parts = []
        for name in self.modality_order:
            value = modalities.get(name)
            parts.append(value if value is not None else torch.zeros(batch, self.modality_dims[name], device=present[0].device, dtype=present[0].dtype))
        return torch.cat(parts, dim=-1)

    def _tokens(self, modalities: Mapping[str, Tensor]) -> Tensor:
        tokens = []
        for name, adapter in self.adapters.items():
            value = modalities.get(name)
            if value is not None:
                tokens.append(torch.tanh(adapter(value)).unsqueeze(1))
        if not tokens:
            raise ValueError("at least one declared modality must be supplied")
        return torch.cat(tokens, dim=1)

    def forward(self, modalities: Mapping[str, Tensor], wave_numbers: Tensor, *,
                noise: Tensor | None = None, stochastic: bool = False) -> GeneralistOutput:
        tokens = self._tokens(modalities)
        psi = self.to_spectral(tokens)
        spectral = self.field(psi, wave_numbers, noise=noise, stochastic=stochastic)
        # Spectral coefficients gate each shared token before workspace broadcast.
        gated = (tokens * torch.sigmoid(spectral.field.mean(dim=-1, keepdim=True))
                 if self.use_spectral_field else tokens)
        workspace = self.workspace(gated)
        pooled = workspace.mean(dim=1)
        ood_distance = (pooled - self.in_distribution_center.to(pooled)).square().mean(dim=-1, keepdim=True)
        raw_distance = (self._raw_features(modalities) - self.raw_input_center.to(pooled)).square().mean(dim=-1, keepdim=True)
        uncertainty = F.softplus(self.uncertainty_head(pooled)) + ood_distance + raw_distance
        return GeneralistOutput(self.classification_head(pooled), self.regression_head(pooled),
                                self.time_series_head(pooled), self.reconstruction_head(pooled),
                                uncertainty, spectral, workspace)
