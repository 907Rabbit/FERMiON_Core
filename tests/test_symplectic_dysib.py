from __future__ import annotations

from dataclasses import replace

import torch

from fermion_symplectic_dysib import (
    BenchmarkConfig,
    BenchmarkMetrics,
    DySIBEncoder,
    GSEDiagnosticHook,
    InfoNCELoss,
    RolloutLoss,
    SymplecticTransition,
    promotion_decision,
    run_benchmark,
    simulate_double_pendulum,
    simulate_pendulum,
    symplecticity_error,
)


def test_symplectic_transition_preserves_canonical_form():
    torch.manual_seed(4)
    transition = SymplecticTransition(4).double()
    error = symplecticity_error(transition, torch.randn(4, dtype=torch.float64))
    assert error < 1e-10


def test_encoder_and_losses_are_differentiable():
    encoder = DySIBEncoder(4, 4)
    transition = SymplecticTransition(4)
    observations = torch.randn(8, 4)
    latent = encoder(observations)
    predicted = transition(latent)
    targets = torch.stack((latent.detach(), latent.detach()), dim=1)
    loss = InfoNCELoss()(predicted, latent.detach()) + RolloutLoss()(transition, latent, targets)
    loss.backward()
    assert torch.isfinite(loss)
    assert encoder.network[0].weight.grad is not None


def test_pendulum_generators_have_expected_finite_shapes():
    generator = torch.Generator().manual_seed(9)
    single = simulate_pendulum(5, 7, 0.02, generator)
    double = simulate_double_pendulum(5, 7, 0.02, generator)
    assert single.shape == double.shape == (5, 8, 4)
    assert torch.isfinite(single).all() and torch.isfinite(double).all()


def test_gse_diagnostics_are_finite_and_named():
    diagnostic = GSEDiagnosticHook()(torch.randn(4, 8, 4))
    values = vars(diagnostic)
    assert set(values) == {"I1", "I2", "I3", "I4", "Delta_G_norm",
                           "curvature_proxy", "transition_spike_score"}
    assert all(torch.isfinite(torch.tensor(value)) for value in values.values())


def test_quick_benchmark_reports_all_models_and_outputs():
    config = BenchmarkConfig(trajectories=8, steps=6, pretrain_epochs=1,
                             finetune_epochs=1, batch_size=32)
    results = run_benchmark(config)
    assert set(results) == {"pca", "autoencoder", "vae", "dysib", "symplectic_dysib"}
    for metrics in results.values():
        assert metrics.rollout_error >= 0
        assert metrics.energy_drift >= 0
        assert metrics.parameter_count > 0
    assert results["symplectic_dysib"].symplecticity_error < 1e-4


def test_promotion_requires_three_improvements_and_acceptable_cost():
    base = BenchmarkMetrics(2, 2, 2, 1, 1, 2, 0.2, 100, 1, 0, 0, 0, 0, 0, 0, 0)
    strong = replace(base, rollout_error=1, energy_drift=1, symplecticity_error=1,
                     interpretability=0.3, parameter_count=200, runtime_seconds=2)
    accepted = promotion_decision({"dysib": base, "symplectic_dysib": strong})
    assert accepted.promoted and accepted.cost_acceptable
    expensive = replace(strong, parameter_count=300)
    rejected = promotion_decision({"dysib": base, "symplectic_dysib": expensive})
    assert not rejected.promoted and not rejected.cost_acceptable
