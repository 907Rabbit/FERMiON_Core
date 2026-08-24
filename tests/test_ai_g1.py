"""AI-G1 acceptance tests.  These do not exercise or alter FERMiON-HR-193."""

from __future__ import annotations

import torch
from torch.nn import functional as F

from fermion.ai_g1 import (GaussianSpectralOracle, LearnableSpectralField,
                           MLPBaseline, MultimodalSpectralGeneralist,
                           ReplayBuffer, TransformerBaseline)


def _modes(batch: int = 4, modes: int = 8) -> torch.Tensor:
    return torch.linspace(0.0, 2.0, modes, dtype=torch.float64).repeat(batch, 1)


def test_fixed_oracle_is_reproduced_by_learnable_initialization():
    oracle = GaussianSpectralOracle(a=0.7, mass_squared=0.4, sigma=0.2)
    layer = LearnableSpectralField.from_oracle(oracle)
    psi = torch.randn(4, 8, dtype=torch.float64)
    noise = torch.randn_like(psi)
    expected = oracle(psi, _modes(), noise=noise)
    actual = layer(psi, _modes(), noise=noise)
    assert torch.allclose(actual.field, expected.field, rtol=0.0, atol=2e-15)
    assert torch.allclose(actual.mean, expected.mean, rtol=0.0, atol=2e-15)


def test_spectral_autodiff_matches_finite_difference():
    layer = LearnableSpectralField()
    psi = torch.randn(2, 8, dtype=torch.float64)
    modes = _modes(2)
    layer(psi, modes, stochastic=False).mean.square().sum().backward()
    analytic = layer.raw_a.grad.item()
    delta = 1e-6
    with torch.no_grad():
        original = layer.raw_a.item()
        layer.raw_a.copy_(torch.tensor(original + delta, dtype=torch.float64))
        plus = layer(psi, modes, stochastic=False).mean.square().sum().item()
        layer.raw_a.copy_(torch.tensor(original - delta, dtype=torch.float64))
        minus = layer(psi, modes, stochastic=False).mean.square().sum().item()
        layer.raw_a.copy_(torch.tensor(original, dtype=torch.float64))
    assert abs(analytic - (plus - minus) / (2 * delta)) / max(1.0, abs(analytic)) < 1e-5
    assert layer.source_coefficients.grad is not None


def test_deterministic_and_stochastic_spectral_modes():
    layer = LearnableSpectralField()
    psi, modes = torch.ones(3, 8, dtype=torch.float64), _modes(3)
    mean = layer(psi, modes, stochastic=False)
    sample_a = layer(psi, modes, noise=torch.zeros_like(psi), stochastic=True)
    sample_b = layer(psi, modes, noise=torch.ones_like(psi), stochastic=True)
    assert torch.equal(mean.field, mean.mean) and torch.equal(sample_a.field, mean.mean)
    assert not torch.equal(sample_b.field, mean.mean)


def test_one_shared_core_exposes_all_four_task_heads():
    model = MultimodalSpectralGeneralist({"text": 5, "sensor": 3}, reconstruction_dim=5)
    inputs = {"text": torch.randn(4, 5), "sensor": torch.randn(4, 3)}
    output = model(inputs, torch.linspace(0, 1, 8).repeat(4, 1))
    assert output.classification.shape == (4, 2)
    assert output.regression.shape == (4, 1)
    assert output.time_series.shape == (4, 3)
    assert output.reconstruction.shape == (4, 5)
    assert output.workspace.shape[:2] == (4, 2)


def test_replay_retains_a_simple_earlier_task_within_five_percent():
    torch.manual_seed(7)
    model = MLPBaseline(2, 16, 2)
    head_b = torch.nn.Linear(16, 1)
    # Train task A on a separable classification relation.
    x_a = torch.randn(96, 2); y_a = (x_a[:, 0] > 0).long()
    trunk = model.net[0:2]
    classifier = model.net[2]
    opt_a = torch.optim.Adam(model.parameters(), lr=0.03)
    for _ in range(80):
        loss = F.cross_entropy(model(x_a), y_a); opt_a.zero_grad(); loss.backward(); opt_a.step()
    before = (model(x_a).argmax(-1) == y_a).float().mean().item()
    replay = ReplayBuffer(96)
    for x, y in zip(x_a, y_a): replay.append(x=x, y=y)
    x_b = torch.randn(96, 2); y_b = (0.6 * x_b[:, 0] - 0.2 * x_b[:, 1]).unsqueeze(-1)
    opt_b = torch.optim.Adam(list(model.parameters()) + list(head_b.parameters()), lr=0.01)
    for _ in range(100):
        batch = replay.sample(32)
        shared_b = trunk(x_b)
        shared_a = trunk(batch["x"])
        loss = F.mse_loss(head_b(shared_b), y_b) + F.cross_entropy(classifier(shared_a), batch["y"])
        opt_b.zero_grad(); loss.backward(); opt_b.step()
    after = (model(x_a).argmax(-1) == y_a).float().mean().item()
    assert after >= before - 0.05


def test_uncertainty_increases_for_ood_inputs():
    model = MultimodalSpectralGeneralist({"sensor": 3})
    in_distribution = {"sensor": torch.zeros(12, 3)}
    model.set_in_distribution_reference(in_distribution)
    modes = torch.linspace(0, 1, 8).repeat(12, 1)
    known = model(in_distribution, modes).uncertainty.mean()
    unknown = model({"sensor": torch.full((12, 3), 8.0)}, modes).uncertainty.mean()
    assert unknown > known


def test_matched_mlp_and_transformer_baselines_are_available():
    assert MLPBaseline(6, 12, 2)(torch.randn(3, 6)).shape == (3, 2)
    assert TransformerBaseline(8, 2)(torch.randn(3, 4, 8)).shape == (3, 2)
