"""AI-G2S spectral-utility tasks, controls, paired statistics, and baselines.

This module supplies evaluation machinery.  It intentionally has no promotion
logic: an experiment must earn a pass through :func:`spectral_utility_gate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import torch
from torch import Tensor, nn
from torch.nn import functional as F


@dataclass(frozen=True)
class SpectralTask:
    name: str
    train_input: Tensor
    train_target: Tensor
    test_input: Tensor
    test_target: Tensor
    wave_numbers: Tensor
    spectral_aligned: bool


class TinyCNNBaseline(nn.Module):
    def __init__(self, channels: int = 1, width: int = 12) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(channels, width, 3, padding=1), nn.GELU(),
                                 nn.Conv2d(width, channels, 3, padding=1))

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


class TinyFourierOperatorBaseline(nn.Module):
    """Small learnable low-mode Fourier operator baseline (not a full FNO)."""
    def __init__(self, modes: int = 6) -> None:
        super().__init__()
        self.modes = modes
        self.weight = nn.Parameter(torch.ones(modes, modes, dtype=torch.complex64))

    def forward(self, x: Tensor) -> Tensor:
        spectrum = torch.fft.rfft2(x)
        height, width = min(self.modes, spectrum.shape[-2]), min(self.modes, spectrum.shape[-1])
        scaled = spectrum.clone()
        scaled[..., :height, :width] *= self.weight[:height, :width]
        return torch.fft.irfft2(scaled, s=x.shape[-2:])


def poisson_darcy_task(*, train_samples: int = 48, test_samples: int = 24, modes: int = 32,
                      seed: int = 0) -> SpectralTask:
    """1-D periodic Poisson/Darcy-like inverse operator with unseen forcing."""
    generator = torch.Generator().manual_seed(seed)
    k = torch.arange(1, modes + 1, dtype=torch.float32)
    forcing = torch.randn(train_samples + test_samples, modes, generator=generator)
    operator = 1.0 / (0.2 + k.square())
    target = forcing * operator
    return SpectralTask("poisson_darcy", forcing[:train_samples], target[:train_samples], forcing[train_samples:],
                        target[train_samples:], k, True)


def cross_resolution_task(*, train_resolution: int = 32, test_resolution: int = 64,
                          samples: int = 24, seed: int = 0) -> SpectralTask:
    """Smooth field mapping trained at one grid resolution and evaluated at another."""
    generator = torch.Generator().manual_seed(seed)
    def field(size: int) -> tuple[Tensor, Tensor]:
        x = torch.linspace(0, 2 * torch.pi, size)
        y = torch.linspace(0, 2 * torch.pi, size)
        yy, xx = torch.meshgrid(y, x, indexing="ij")
        coefficients = torch.randn(samples, 3, generator=generator)
        value = sum(coefficients[:, index, None, None] * torch.sin((index + 1) * xx + (index + 2) * yy)
                    for index in range(3))
        target = value + 0.3 * torch.cos(2 * xx - yy)
        return value.unsqueeze(1), target.unsqueeze(1)
    train_x, train_y = field(train_resolution); test_x, test_y = field(test_resolution)
    return SpectralTask("cross_resolution", train_x, train_y, test_x, test_y,
                        torch.arange(train_resolution, dtype=torch.float32), True)


def multiscale_forecast_task(*, train_samples: int = 64, test_samples: int = 32,
                             context: int = 32, horizon: int = 8, seed: int = 0) -> SpectralTask:
    """Forecast a mixture of long/short periodic components; test uses held-out regimes."""
    generator = torch.Generator().manual_seed(seed)
    count = train_samples + test_samples
    frequency = torch.rand(count, 2, generator=generator) * torch.tensor([0.14, 0.45]) + torch.tensor([0.02, 0.12])
    phase = torch.rand(count, 2, generator=generator) * (2 * torch.pi)
    time = torch.arange(context + horizon, dtype=torch.float32)
    series = (torch.sin(frequency[:, :1] * time + phase[:, :1])
              + 0.45 * torch.sin(frequency[:, 1:] * time + phase[:, 1:]))
    return SpectralTask("multiscale_forecast", series[:train_samples, :context], series[:train_samples, context:],
                        series[train_samples:, :context], series[train_samples:, context:],
                        torch.fft.rfftfreq(context), True)


def permuted_coordinate_control(task: SpectralTask, seed: int = 0) -> SpectralTask:
    """Negative control: destroy coordinate-frequency correspondence only."""
    generator = torch.Generator().manual_seed(seed)
    if task.train_input.ndim != 2:
        raise ValueError("permuted-coordinate control currently expects vector data")
    order = torch.randperm(task.train_input.shape[-1], generator=generator)
    return SpectralTask(task.name + "_permuted", task.train_input[:, order], task.train_target,
                        task.test_input[:, order], task.test_target, task.wave_numbers[order], False)


def tabular_control(*, train_samples: int = 64, test_samples: int = 32, features: int = 12,
                    seed: int = 0) -> SpectralTask:
    generator = torch.Generator().manual_seed(seed)
    x = torch.randn(train_samples + test_samples, features, generator=generator)
    y = (x[:, :1] * x[:, 1:2] + 0.2 * x[:, 2:3].square())
    return SpectralTask("tabular_control", x[:train_samples], y[:train_samples], x[train_samples:], y[train_samples:],
                        torch.arange(features, dtype=torch.float32), False)


def paired_bootstrap_interval(deltas: Tensor, *, resamples: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean paired error delta and a deterministic 95% bootstrap interval."""
    if deltas.ndim != 1 or len(deltas) < 2:
        raise ValueError("at least two paired seed deltas are required")
    generator = torch.Generator().manual_seed(seed)
    indices = torch.randint(len(deltas), (resamples, len(deltas)), generator=generator)
    means = deltas[indices].mean(dim=1)
    return float(deltas.mean()), float(torch.quantile(means, 0.025)), float(torch.quantile(means, 0.975))


def spectral_utility_gate(task_deltas: Mapping[str, Tensor], *, min_relative_improvement: float = 0.05,
                          spectral_tasks_required: int = 2) -> dict[str, object]:
    """Decide a gate from paired relative error deltas (spectral - ablation)."""
    details = {}
    wins = 0
    for name, deltas in task_deltas.items():
        mean, low, high = paired_bootstrap_interval(deltas)
        passed = mean <= -min_relative_improvement and high < 0.0
        details[name] = {"mean_relative_delta": mean, "ci95": (low, high), "passes": passed}
        wins += int(passed)
    return {"passed": wins >= spectral_tasks_required, "spectral_task_wins": wins,
            "required_wins": spectral_tasks_required, "details": details}
