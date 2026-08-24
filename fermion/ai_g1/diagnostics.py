"""Non-invasive diagnostics for the AI-G1 diagonal spectral layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

import torch
from torch import Tensor

from .spectral import LearnableSpectralField, SpectralFieldOutput


@dataclass(frozen=True)
class SpectralDiagnosticReport:
    scale: float
    mass_squared: float
    sigma: float
    source_coefficients: tuple[float, ...]
    transfer_mean: float
    transfer_std: float
    spectral_activation_norm: float
    residual_activation_norm: float
    spectral_to_residual_ratio: float
    gate_mean: float
    gate_std: float
    gradient_norms: dict[str, float]
    frequency_error: tuple[float, ...]
    collapse_flags: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def frequency_resolved_mse(prediction: Tensor, target: Tensor, bins: int = 4) -> tuple[float, ...]:
    if prediction.shape != target.shape or prediction.shape[-1] < bins:
        raise ValueError("prediction and target must share a final mode axis at least as large as bins")
    errors = (prediction - target).square()
    chunks = torch.tensor_split(errors, bins, dim=-1)
    return tuple(float(chunk.mean().detach()) for chunk in chunks)


def inspect_spectral_layer(layer: LearnableSpectralField, output: SpectralFieldOutput, *,
                           residual: Tensor, target: Tensor | None = None,
                           collapse_tolerance: float = 1e-4) -> SpectralDiagnosticReport:
    transfer = output.transfer.detach()
    spectral_norm = float(torch.linalg.vector_norm(output.field.detach()))
    residual_norm = float(torch.linalg.vector_norm(residual.detach()))
    gate = torch.sigmoid(output.field.detach().mean(dim=-1))
    gradients = {name: (float(torch.linalg.vector_norm(parameter.grad.detach())) if parameter.grad is not None else 0.0)
                 for name, parameter in layer.named_parameters()}
    flags = []
    if float((transfer - 1.0).abs().mean()) < collapse_tolerance:
        flags.append("identity_transfer")
    if float(transfer.abs().mean()) < collapse_tolerance:
        flags.append("zero_coupling")
    if float(layer.a.detach()) > 1e3 or float(layer.mass_squared.detach()) > 1e3:
        flags.append("excessive_smoothing")
    if spectral_norm < collapse_tolerance:
        flags.append("silent_spectral_activation")
    return SpectralDiagnosticReport(
        scale=float(layer.a.detach()), mass_squared=float(layer.mass_squared.detach()), sigma=float(layer.sigma.detach()),
        source_coefficients=tuple(float(value) for value in layer.source_coefficients.detach()),
        transfer_mean=float(transfer.mean()), transfer_std=float(transfer.std()),
        spectral_activation_norm=spectral_norm, residual_activation_norm=residual_norm,
        spectral_to_residual_ratio=spectral_norm / max(residual_norm, 1e-12),
        gate_mean=float(gate.mean()), gate_std=float(gate.std()), gradient_norms=gradients,
        frequency_error=frequency_resolved_mse(output.mean, target) if target is not None else (),
        collapse_flags=tuple(flags),
    )
