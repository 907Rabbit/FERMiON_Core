"""Strict versioned checkpoints for production FERMiON-HR."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch
from torch import Tensor, nn

from .config import HRConfig

CHECKPOINT_FORMAT = 1


def _config_digest(config: HRConfig) -> str:
    payload = json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def save_checkpoint(path: str | Path, model: nn.Module, config: HRConfig, psi: Tensor,
                    memory: Tensor, optimizer: torch.optim.Optimizer | None = None,
                    metadata: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "format": CHECKPOINT_FORMAT,
        "architecture": "FERMiON-HR",
        "config": config.to_dict(),
        "config_digest": _config_digest(config),
        "state_dict": model.state_dict(),
        "parameter_layout": tuple((name, tuple(parameter.shape)) for name, parameter in model.named_parameters()),
        "psi": psi.detach().cpu(),
        "memory": memory.detach().cpu(),
        "metadata": metadata or {},
    }
    if optimizer is not None:
        payload["optimizer"] = optimizer.state_dict()
    torch.save(payload, path)


def load_checkpoint(path: str | Path, model: nn.Module, config: HRConfig,
                    optimizer: torch.optim.Optimizer | None = None) -> tuple[Tensor, Tensor, dict[str, Any]]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if payload.get("format") != CHECKPOINT_FORMAT or payload.get("architecture") != "FERMiON-HR":
        raise ValueError("incompatible FERMiON-HR checkpoint format")
    if payload.get("config_digest") != _config_digest(config):
        raise ValueError("checkpoint configuration does not match this model")
    expected = tuple((name, tuple(parameter.shape)) for name, parameter in model.named_parameters())
    if tuple(payload.get("parameter_layout", ())) != expected:
        raise ValueError("checkpoint parameter layout is incompatible")
    model.load_state_dict(payload["state_dict"], strict=True)
    if optimizer is not None and "optimizer" in payload:
        optimizer.load_state_dict(payload["optimizer"])
    return payload["psi"], payload["memory"], payload.get("metadata", {})

