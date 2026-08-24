from __future__ import annotations

import torch

from fermion.ai_g1.ai_g2s import (TinyCNNBaseline, TinyFourierOperatorBaseline, cross_resolution_task,
                                  multiscale_forecast_task, paired_bootstrap_interval, permuted_coordinate_control,
                                  poisson_darcy_task, spectral_utility_gate, tabular_control)
from fermion.ai_g1.diagnostics import inspect_spectral_layer
from fermion.ai_g1.spectral import LearnableSpectralField


def test_spectral_diagnostics_report_parameters_gradients_frequency_and_collapse():
    layer = LearnableSpectralField()
    psi = torch.randn(3, 8, dtype=torch.float64, requires_grad=True)
    modes = torch.linspace(0, 2, 8, dtype=torch.float64).repeat(3, 1)
    output = layer(psi, modes, stochastic=False)
    output.mean.square().sum().backward()
    report = inspect_spectral_layer(layer, output, residual=psi, target=torch.zeros_like(psi))
    assert report.gradient_norms["raw_a"] > 0 and len(report.frequency_error) == 4
    assert "identity_transfer" in report.collapse_flags


def test_spectral_aligned_tasks_and_negative_controls_have_declared_shapes():
    poisson = poisson_darcy_task(modes=16)
    cross = cross_resolution_task(train_resolution=16, test_resolution=32, samples=5)
    forecast = multiscale_forecast_task(train_samples=8, test_samples=4)
    assert poisson.train_input.shape == poisson.train_target.shape == (48, 16)
    assert cross.train_input.shape[-2:] == (16, 16) and cross.test_input.shape[-2:] == (32, 32)
    assert forecast.train_input.shape[-1] == 32 and forecast.train_target.shape[-1] == 8
    assert not permuted_coordinate_control(poisson).spectral_aligned and not tabular_control().spectral_aligned


def test_cnn_and_small_fourier_operator_baselines_execute():
    image = torch.randn(2, 1, 16, 16)
    assert TinyCNNBaseline()(image).shape == image.shape
    assert TinyFourierOperatorBaseline()(image).shape == image.shape


def test_paired_gate_requires_two_confident_spectral_wins_and_rejects_null():
    good = torch.tensor([-0.10, -0.08, -0.07, -0.09])
    null = torch.tensor([0.01, -0.01, 0.02, -0.02])
    mean, low, high = paired_bootstrap_interval(good, resamples=200)
    assert mean < -0.05 and high < 0
    passed = spectral_utility_gate({"poisson": good, "forecast": good, "tabular": null})
    rejected = spectral_utility_gate({"poisson": good, "forecast": null})
    assert passed["passed"] and not rejected["passed"]
