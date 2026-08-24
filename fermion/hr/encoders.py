"""Availability-aware multimodal observation encoding."""

from __future__ import annotations

import torch
from torch import Tensor, nn

from .config import HRConfig


class MultimodalEncoder(nn.Module):
    def __init__(self, config: HRConfig):
        super().__init__()
        self.config = config
        self.names = tuple(config.modality_dims)
        per_modality = max(4, config.encoded_dim // len(self.names))
        self.encoders = nn.ModuleDict({
            name: nn.Sequential(nn.Linear(size, per_modality), nn.LayerNorm(per_modality), nn.Tanh())
            for name, size in config.modality_dims.items()
        })
        self.fusion = nn.Linear(per_modality * len(self.names) + len(self.names), config.encoded_dim)

    def forward(self, observations: dict[str, Tensor | None]) -> tuple[Tensor, Tensor]:
        present = [value for value in observations.values() if value is not None]
        if not present:
            raise ValueError("at least one observation modality is required")
        batch_shape = present[0].shape[:-1]
        dtype, device = present[0].dtype, present[0].device
        encoded: list[Tensor] = []
        masks: list[Tensor] = []
        for name in self.names:
            value = observations.get(name)
            available = value is not None
            if value is None:
                value = torch.zeros(*batch_shape, self.config.modality_dims[name], dtype=dtype, device=device)
            if value.shape[:-1] != batch_shape or value.shape[-1] != self.config.modality_dims[name]:
                raise ValueError(f"invalid shape for modality {name}: {tuple(value.shape)}")
            mask = torch.full((*batch_shape, 1), float(available), dtype=dtype, device=device)
            encoded.append(self.encoders[name](value) * mask)
            masks.append(mask)
        availability = torch.cat(masks, dim=-1)
        return torch.tanh(self.fusion(torch.cat((*encoded, availability), dim=-1))), availability

