"""Differentiable Gaussian and learnable spectral-field layers for AI-G1."""

from __future__ import annotations

from dataclasses import dataclass
import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F


def _radial_frequency_squared(wave_numbers: Tensor) -> Tensor:
    """Return |k|² for scalar modes (..., modes) or vector modes (..., modes, d)."""
    if wave_numbers.ndim < 1:
        raise ValueError("wave_numbers must have at least one dimension")
    # A final coordinate dimension is unambiguous for the common (..., modes, d)
    # representation. Scalar spectral grids remain (..., modes).
    if wave_numbers.ndim >= 3:
        return wave_numbers.square().sum(dim=-1)
    return wave_numbers.square()


def _inverse_softplus(value: float) -> float:
    if value <= 0:
        raise ValueError("positive physical values are required")
    return math.log(math.expm1(value))


@dataclass(frozen=True)
class SpectralFieldOutput:
    field: Tensor
    mean: Tensor
    denominator: Tensor
    transfer: Tensor
    standard_deviation: Tensor


class GaussianSpectralOracle(nn.Module):
    """Fixed formulation used as the AI-G1 spectral regression oracle.

    u_k = B(k) psi_k / (a |k|² + m² + eps)
          + sigma eta_k / sqrt(a |k|² + m² + eps)
    """

    def __init__(self, a: float = 0.8, mass_squared: float = 0.35,
                 sigma: float = 0.15, eps: float = 1e-7) -> None:
        super().__init__()
        if a <= 0 or mass_squared <= 0 or sigma < 0 or eps <= 0:
            raise ValueError("invalid Gaussian spectral parameters")
        self.a, self.mass_squared, self.sigma, self.eps = a, mass_squared, sigma, eps

    def forward(self, psi: Tensor, wave_numbers: Tensor, *, noise: Tensor | None = None,
                source_coupling: Tensor | None = None, stochastic: bool = True) -> SpectralFieldOutput:
        k2 = _radial_frequency_squared(wave_numbers).to(dtype=psi.dtype, device=psi.device)
        denominator = self.a * k2 + self.mass_squared + self.eps
        transfer = torch.ones_like(denominator) if source_coupling is None else source_coupling
        # A single spectral grid may be shared by multiple modality tokens.
        while denominator.ndim < psi.ndim:
            denominator = denominator.unsqueeze(-2)
            transfer = transfer.unsqueeze(-2)
        mean = transfer * psi / denominator
        standard_deviation = self.sigma / torch.sqrt(denominator)
        if stochastic:
            eta = torch.randn_like(mean) if noise is None else noise.to(dtype=psi.dtype, device=psi.device)
            field = mean + standard_deviation * eta
        else:
            field = mean
        return SpectralFieldOutput(field, mean, denominator, transfer, standard_deviation)


class LearnableSpectralField(nn.Module):
    """Backpropagated spectral field with learnable scale, mass, noise and B(k).

    The source transfer starts at B(k)=1.  Its three coefficients learn a smooth
    radial correction, leaving the fixed Gaussian oracle exactly reproducible at
    initialization through :meth:`from_oracle`.
    """

    def __init__(self, *, a: float = 0.8, mass_squared: float = 0.35,
                 sigma: float = 0.15, eps: float = 1e-7) -> None:
        super().__init__()
        self.raw_a = nn.Parameter(torch.tensor(_inverse_softplus(a), dtype=torch.float64))
        self.raw_mass_squared = nn.Parameter(torch.tensor(_inverse_softplus(mass_squared), dtype=torch.float64))
        self.raw_sigma = nn.Parameter(torch.tensor(_inverse_softplus(max(sigma, 1e-12)), dtype=torch.float64))
        self.source_coefficients = nn.Parameter(torch.zeros(3, dtype=torch.float64))
        self.eps = eps

    @classmethod
    def from_oracle(cls, oracle: GaussianSpectralOracle) -> "LearnableSpectralField":
        return cls(a=oracle.a, mass_squared=oracle.mass_squared, sigma=oracle.sigma, eps=oracle.eps)

    @property
    def a(self) -> Tensor:
        return F.softplus(self.raw_a)

    @property
    def mass_squared(self) -> Tensor:
        return F.softplus(self.raw_mass_squared)

    @property
    def sigma(self) -> Tensor:
        return F.softplus(self.raw_sigma)

    def source_coupling(self, radial_squared: Tensor) -> Tensor:
        scale = radial_squared / (1.0 + radial_squared)
        features = torch.stack((torch.ones_like(scale), scale, scale.square()), dim=-1)
        return 1.0 + torch.einsum("...f,f->...", features, self.source_coefficients.to(scale))

    def forward(self, psi: Tensor, wave_numbers: Tensor, *, noise: Tensor | None = None,
                stochastic: bool = True) -> SpectralFieldOutput:
        k2 = _radial_frequency_squared(wave_numbers).to(dtype=psi.dtype, device=psi.device)
        a, mass_squared, sigma = self.a.to(psi), self.mass_squared.to(psi), self.sigma.to(psi)
        denominator = a * k2 + mass_squared + self.eps
        transfer = self.source_coupling(k2)
        # Broadcast a shared mode grid over any token/channel axis in psi.
        while denominator.ndim < psi.ndim:
            denominator = denominator.unsqueeze(-2)
            transfer = transfer.unsqueeze(-2)
        mean = transfer * psi / denominator
        standard_deviation = sigma / torch.sqrt(denominator)
        if stochastic:
            eta = torch.randn_like(mean) if noise is None else noise.to(dtype=psi.dtype, device=psi.device)
            field = mean + standard_deviation * eta
        else:
            field = mean
        return SpectralFieldOutput(field, mean, denominator, transfer, standard_deviation)
