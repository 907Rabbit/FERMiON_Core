"""Phase 17B.2: experimental Symplectic DySIB coordinate discovery.

This module turns the research sketch into a falsifiable benchmark.  The four
I-diagnostics are operational statistics, not claims that the learned latent
variables are physical fields or conscious states.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

import torch
from torch import Tensor, nn
from torch.nn import functional as F


def _linear(in_features: int, out_features: int) -> nn.Linear:
    layer = nn.Linear(in_features, out_features)
    nn.init.xavier_uniform_(layer.weight)
    nn.init.zeros_(layer.bias)
    return layer


class DySIBEncoder(nn.Module):
    """Compact observation encoder with an optional variational posterior."""

    def __init__(self, observation_dim: int, latent_dim: int, hidden_dim: int = 64,
                 variational: bool = False):
        super().__init__()
        if latent_dim < 2:
            raise ValueError("latent_dim must be at least two")
        self.latent_dim = latent_dim
        self.variational = variational
        output_dim = latent_dim * (2 if variational else 1)
        self.network = nn.Sequential(
            _linear(observation_dim, hidden_dim), nn.Tanh(),
            _linear(hidden_dim, hidden_dim), nn.Tanh(),
            _linear(hidden_dim, output_dim),
        )

    def distribution(self, observation: Tensor) -> tuple[Tensor, Tensor]:
        output = self.network(observation)
        if not self.variational:
            return output, torch.zeros_like(output)
        mean, log_variance = output.chunk(2, dim=-1)
        return mean, log_variance.clamp(-12.0, 8.0)

    def forward(self, observation: Tensor) -> Tensor:
        mean, log_variance = self.distribution(observation)
        if self.variational and self.training:
            return mean + torch.exp(0.5 * log_variance) * torch.randn_like(mean)
        return mean


class _PotentialGradient(nn.Module):
    """Gradient of sum_i scale_i log(cosh(w_i x + b_i))."""

    def __init__(self, dimension: int, hidden_dim: int):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(hidden_dim, dimension))
        self.bias = nn.Parameter(torch.zeros(hidden_dim))
        self.scale = nn.Parameter(torch.empty(hidden_dim))
        nn.init.xavier_uniform_(self.weight)
        nn.init.uniform_(self.scale, -0.05, 0.05)

    def forward(self, value: Tensor) -> Tensor:
        activation = torch.tanh(F.linear(value, self.weight, self.bias)) * self.scale
        return F.linear(activation, self.weight.t())


class LA_SympNetBlock(nn.Module):
    """Two exact symplectic shears over canonical coordinates ``[q, p]``."""

    def __init__(self, latent_dim: int, hidden_dim: int = 32, step_size: float = 0.05):
        super().__init__()
        if latent_dim % 2:
            raise ValueError("a symplectic latent dimension must be even")
        half = latent_dim // 2
        self.q_potential = _PotentialGradient(half, hidden_dim)
        self.p_potential = _PotentialGradient(half, hidden_dim)
        self.step_size = step_size

    def forward(self, state: Tensor) -> Tensor:
        q, p = state.chunk(2, dim=-1)
        q_next = q + self.step_size * self.p_potential(p)
        p_next = p - self.step_size * self.q_potential(q_next)
        return torch.cat((q_next, p_next), dim=-1)


class SymplecticTransition(nn.Module):
    def __init__(self, latent_dim: int, blocks: int = 3, hidden_dim: int = 32,
                 step_size: float = 0.05):
        super().__init__()
        self.latent_dim = latent_dim
        self.blocks = nn.ModuleList(
            LA_SympNetBlock(latent_dim, hidden_dim, step_size / blocks) for _ in range(blocks)
        )

    def forward(self, state: Tensor) -> Tensor:
        for block in self.blocks:
            state = block(state)
        return state


class FeedForwardTransition(nn.Module):
    def __init__(self, latent_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.network = nn.Sequential(_linear(latent_dim, hidden_dim), nn.Tanh(),
                                     _linear(hidden_dim, latent_dim))

    def forward(self, state: Tensor) -> Tensor:
        return state + self.network(state)


class InfoNCELoss(nn.Module):
    def __init__(self, temperature: float = 0.1):
        super().__init__()
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        self.temperature = temperature

    def forward(self, prediction: Tensor, positive: Tensor) -> Tensor:
        prediction = F.normalize(prediction, dim=-1)
        positive = F.normalize(positive, dim=-1)
        logits = prediction @ positive.t() / self.temperature
        labels = torch.arange(logits.shape[0], device=logits.device)
        return F.cross_entropy(logits, labels)


class RolloutLoss(nn.Module):
    def __init__(self, discount: float = 1.0):
        super().__init__()
        self.discount = discount

    def forward(self, transition: nn.Module, initial: Tensor, targets: Tensor) -> Tensor:
        state = initial
        total = initial.new_zeros(())
        normalization = 0.0
        for step in range(targets.shape[1]):
            state = transition(state)
            weight = self.discount ** step
            total = total + weight * F.mse_loss(state, targets[:, step])
            normalization += weight
        return total / max(normalization, 1e-12)


@dataclass(frozen=True)
class GSEDiagnostics:
    I1: float
    I2: float
    I3: float
    I4: float
    Delta_G_norm: float
    curvature_proxy: float
    transition_spike_score: float


class GSEDiagnosticHook:
    """Geometry/statistics diagnostics for a latent trajectory.

    I1 is bounded latent variance, I2 temporal coherence, I3 normalized
    participation ratio, and I4 local smoothness.  They are explicitly proxy
    measures and require downstream validation before interpretation.
    """

    @torch.no_grad()
    def __call__(self, latent: Tensor) -> GSEDiagnostics:
        if latent.ndim != 3 or latent.shape[1] < 3:
            raise ValueError("latent must have shape [batch, time>=3, dimension]")
        flat = latent.reshape(-1, latent.shape[-1])
        variance = flat.var(dim=0, unbiased=False)
        i1 = (variance.mean() / (1.0 + variance.mean())).item()
        velocity = latent[:, 1:] - latent[:, :-1]
        acceleration = velocity[:, 1:] - velocity[:, :-1]
        speed = torch.linalg.vector_norm(velocity, dim=-1)
        i2 = (1.0 / (1.0 + acceleration.square().mean())).item()
        eigenvalues = torch.linalg.eigvalsh(torch.cov(flat.t())).clamp_min(0)
        participation = eigenvalues.sum().square() / (eigenvalues.square().sum() + 1e-12)
        i3 = (participation / latent.shape[-1]).item()
        i4 = (1.0 / (1.0 + torch.linalg.vector_norm(acceleration, dim=-1).mean())).item()
        midpoint = max(1, flat.shape[0] // 2)
        first = flat[:midpoint]
        second = flat[midpoint:]
        g_first = torch.cov(first.t()) if first.shape[0] > 1 else torch.zeros_like(torch.cov(flat.t()))
        g_second = torch.cov(second.t()) if second.shape[0] > 1 else g_first
        delta_g = torch.linalg.matrix_norm(g_second - g_first).item()
        curvature = (torch.linalg.vector_norm(acceleration, dim=-1).mean()
                     / (speed.mean() + 1e-12)).item()
        spike = (speed.max() / (speed.median() + 1e-12)).item()
        return GSEDiagnostics(i1, i2, i3, i4, delta_g, curvature, spike)


@dataclass(frozen=True)
class BenchmarkMetrics:
    rollout_error: float
    energy_drift: float
    symplecticity_error: float
    probe_theta_rmse: float
    probe_omega_rmse: float
    noise_robustness: float
    interpretability: float
    parameter_count: int
    runtime_seconds: float
    I1: float
    I2: float
    I3: float
    I4: float
    Delta_G_norm: float
    curvature_proxy: float
    transition_spike_score: float


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    improvements: tuple[str, ...]
    cost_acceptable: bool


@dataclass(frozen=True)
class BenchmarkConfig:
    seed: int = 17
    trajectories: int = 64
    steps: int = 30
    dt: float = 0.04
    latent_dim: int = 4
    pretrain_epochs: int = 8
    finetune_epochs: int = 12
    batch_size: int = 64
    learning_rate: float = 2e-3


class LatentWorldModel(nn.Module):
    def __init__(self, kind: str, observation_dim: int = 4, latent_dim: int = 4):
        super().__init__()
        self.kind = kind
        self.encoder = DySIBEncoder(observation_dim, latent_dim, variational=kind == "vae")
        self.decoder = nn.Sequential(_linear(latent_dim, 64), nn.Tanh(), _linear(64, observation_dim))
        self.transition = (SymplecticTransition(latent_dim) if kind == "symplectic_dysib"
                           else FeedForwardTransition(latent_dim))

    def encode(self, value: Tensor) -> Tensor:
        return self.encoder(value)

    def decode(self, value: Tensor) -> Tensor:
        return self.decoder(value)


class PCAWorldModel(nn.Module):
    def __init__(self, observation_dim: int = 4, latent_dim: int = 4):
        super().__init__()
        self.register_buffer("mean", torch.zeros(observation_dim))
        self.register_buffer("components", torch.eye(observation_dim)[:latent_dim])
        self.transition = nn.Linear(latent_dim, latent_dim)
        for parameter in self.transition.parameters():
            parameter.requires_grad_(False)

    @torch.no_grad()
    def fit(self, sequence: Tensor) -> None:
        flat = sequence.reshape(-1, sequence.shape[-1])
        self.mean.copy_(flat.mean(0))
        _, _, vh = torch.linalg.svd(flat - self.mean, full_matrices=False)
        self.components.copy_(vh[:self.components.shape[0]])
        current = self.encode(sequence[:, :-1]).reshape(-1, self.components.shape[0])
        following = self.encode(sequence[:, 1:]).reshape(-1, self.components.shape[0])
        design = torch.cat((current, torch.ones_like(current[:, :1])), dim=-1)
        solution = torch.linalg.lstsq(design, following).solution
        self.transition.weight.copy_(solution[:-1].t())
        self.transition.bias.copy_(solution[-1])

    def encode(self, value: Tensor) -> Tensor:
        return (value - self.mean) @ self.components.t()

    def decode(self, value: Tensor) -> Tensor:
        return value @ self.components + self.mean


def _wrap_angle(value: Tensor) -> Tensor:
    return torch.remainder(value + math.pi, 2.0 * math.pi) - math.pi


def simulate_pendulum(trajectories: int, steps: int, dt: float, generator: torch.Generator) -> Tensor:
    theta = (torch.rand(trajectories, generator=generator) * 2.0 - 1.0) * math.pi
    omega = (torch.rand(trajectories, generator=generator) * 2.0 - 1.0) * 1.5
    states = [torch.stack((theta, torch.zeros_like(theta), omega, torch.zeros_like(omega)), -1)]
    for _ in range(steps):
        omega = omega - dt * 9.81 * torch.sin(theta)
        theta = _wrap_angle(theta + dt * omega)
        states.append(torch.stack((theta, torch.zeros_like(theta), omega, torch.zeros_like(omega)), -1))
    return torch.stack(states, dim=1)


def simulate_double_pendulum(trajectories: int, steps: int, dt: float,
                             generator: torch.Generator) -> Tensor:
    theta1 = (torch.rand(trajectories, generator=generator) * 2.0 - 1.0) * 2.4
    theta2 = (torch.rand(trajectories, generator=generator) * 2.0 - 1.0) * 2.4
    omega1 = (torch.rand(trajectories, generator=generator) * 2.0 - 1.0)
    omega2 = (torch.rand(trajectories, generator=generator) * 2.0 - 1.0)
    states = [torch.stack((theta1, theta2, omega1, omega2), -1)]
    for _ in range(steps):
        delta = theta1 - theta2
        denominator = 2.0 - torch.cos(2.0 * delta)
        accel1 = (-9.81 * 3.0 * torch.sin(theta1) - 9.81 * torch.sin(theta1 - 2.0 * theta2)
                  - 2.0 * torch.sin(delta) * (omega2.square() + omega1.square() * torch.cos(delta))) / denominator
        accel2 = (2.0 * torch.sin(delta) * (2.0 * omega1.square() + 2.0 * 9.81 * torch.cos(theta1)
                                             + omega2.square() * torch.cos(delta))) / denominator
        omega1 = omega1 + dt * accel1
        omega2 = omega2 + dt * accel2
        theta1 = _wrap_angle(theta1 + dt * omega1)
        theta2 = _wrap_angle(theta2 + dt * omega2)
        states.append(torch.stack((theta1, theta2, omega1, omega2), -1))
    return torch.stack(states, dim=1)


def double_pendulum_energy(state: Tensor) -> Tensor:
    theta1, theta2, omega1, omega2 = state.unbind(-1)
    kinetic = omega1.square() + 0.5 * omega2.square() + omega1 * omega2 * torch.cos(theta1 - theta2)
    potential = -2.0 * 9.81 * torch.cos(theta1) - 9.81 * torch.cos(theta2)
    return kinetic + potential


def symplecticity_error(transition: nn.Module, sample: Tensor) -> float:
    dimension = sample.shape[-1]
    if dimension % 2:
        return float("inf")
    value = sample.detach().clone().requires_grad_(True)
    jacobian = torch.autograd.functional.jacobian(lambda z: transition(z.unsqueeze(0)).squeeze(0), value)
    half = dimension // 2
    identity = torch.eye(half, dtype=value.dtype, device=value.device)
    omega = torch.cat((torch.cat((torch.zeros_like(identity), identity), 1),
                       torch.cat((-identity, torch.zeros_like(identity)), 1)), 0)
    return torch.linalg.matrix_norm(jacobian.t() @ omega @ jacobian - omega).item()


def _pairs(sequence: Tensor) -> tuple[Tensor, Tensor]:
    return sequence[:, :-1].reshape(-1, sequence.shape[-1]), sequence[:, 1:].reshape(-1, sequence.shape[-1])


def _train(model: LatentWorldModel, sequence: Tensor, epochs: int, config: BenchmarkConfig) -> None:
    current, following = _pairs(sequence)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    contrastive = InfoNCELoss()
    indices = torch.arange(current.shape[0])
    model.train()
    for _ in range(epochs):
        shuffled = indices[torch.randperm(indices.numel())]
        for start in range(0, len(shuffled), config.batch_size):
            selected = shuffled[start:start + config.batch_size]
            x, y = current[selected], following[selected]
            z = model.encode(x)
            z_next = model.encode(y)
            predicted = model.transition(z)
            loss = F.mse_loss(model.decode(z), x) + F.mse_loss(model.decode(predicted), y)
            loss = loss + 0.25 * F.mse_loss(predicted, z_next.detach())
            if model.kind in {"dysib", "symplectic_dysib"} and len(selected) > 1:
                loss = loss + 0.02 * contrastive(predicted, z_next.detach())
            if model.kind == "vae":
                mean, log_variance = model.encoder.distribution(x)
                loss = loss - 1e-3 * 0.5 * (1 + log_variance - mean.square() - log_variance.exp()).mean()
            optimizer.zero_grad(); loss.backward(); optimizer.step()
    model.eval()


@torch.no_grad()
def _rollout(model: nn.Module, sequence: Tensor, noisy: bool = False) -> tuple[Tensor, Tensor]:
    initial = sequence[:, 0]
    if noisy:
        initial = initial + 0.05 * torch.randn_like(initial)
    latent = model.encode(initial)
    latents = [latent]
    decoded = [model.decode(latent)]
    for _ in range(sequence.shape[1] - 1):
        latent = model.transition(latent)
        latents.append(latent)
        decoded.append(model.decode(latent))
    return torch.stack(decoded, 1), torch.stack(latents, 1)


def _linear_probe(train_latent: Tensor, train_observation: Tensor, test_latent: Tensor) -> Tensor:
    design = torch.cat((train_latent, torch.ones_like(train_latent[:, :1])), dim=-1)
    weights = torch.linalg.lstsq(design, train_observation).solution
    test_design = torch.cat((test_latent, torch.ones_like(test_latent[:, :1])), dim=-1)
    return test_design @ weights


def _evaluate(model: nn.Module, train: Tensor, test: Tensor, elapsed: float) -> BenchmarkMetrics:
    predicted, latent = _rollout(model, test)
    noisy_predicted, _ = _rollout(model, test, noisy=True)
    rollout_error = F.mse_loss(predicted, test).item()
    noisy_error = F.mse_loss(noisy_predicted, test).item()
    energy = double_pendulum_energy(predicted)
    drift = (energy - energy[:, :1]).abs().mean().item()
    with torch.no_grad():
        train_latent = model.encode(train.reshape(-1, train.shape[-1]))
        test_latent = model.encode(test.reshape(-1, test.shape[-1]))
        probed = _linear_probe(train_latent, train.reshape(-1, 4), test_latent).reshape_as(test)
    theta_rmse = (probed[..., :2] - test[..., :2]).square().mean().sqrt().item()
    omega_rmse = (probed[..., 2:] - test[..., 2:]).square().mean().sqrt().item()
    diagnostic = GSEDiagnosticHook()(latent)
    symplectic_error = symplecticity_error(model.transition, latent[0, 0])
    parameters = sum(parameter.numel() for parameter in model.parameters())
    return BenchmarkMetrics(
        rollout_error, drift, symplectic_error, theta_rmse, omega_rmse,
        noisy_error / max(rollout_error, 1e-12), 1.0 / (1.0 + theta_rmse + omega_rmse),
        parameters, elapsed, **asdict(diagnostic),
    )


def run_benchmark(config: BenchmarkConfig | None = None) -> dict[str, BenchmarkMetrics]:
    config = config or BenchmarkConfig()
    torch.manual_seed(config.seed)
    generator = torch.Generator().manual_seed(config.seed)
    single = simulate_pendulum(config.trajectories, config.steps, config.dt, generator)
    double = simulate_double_pendulum(config.trajectories, config.steps, config.dt, generator)
    split = max(2, int(config.trajectories * 0.75))
    train, test = double[:split], double[split:]
    results: dict[str, BenchmarkMetrics] = {}
    pca = PCAWorldModel(latent_dim=config.latent_dim)
    start = time.perf_counter(); pca.fit(torch.cat((single, train), 0)); elapsed = time.perf_counter() - start
    results["pca"] = _evaluate(pca, train, test, elapsed)
    for kind in ("autoencoder", "vae", "dysib", "symplectic_dysib"):
        torch.manual_seed(config.seed)
        model = LatentWorldModel(kind, latent_dim=config.latent_dim)
        start = time.perf_counter()
        _train(model, single, config.pretrain_epochs, config)
        _train(model, train, config.finetune_epochs, config)
        results[kind] = _evaluate(model, train, test, time.perf_counter() - start)
    return results


def promotion_decision(results: dict[str, BenchmarkMetrics], maximum_cost_ratio: float = 2.5) -> PromotionDecision:
    candidate = results["symplectic_dysib"]
    baseline = results["dysib"]
    lower_is_better = ("rollout_error", "energy_drift", "symplecticity_error", "noise_robustness")
    improvements = [name for name in lower_is_better
                    if getattr(candidate, name) < getattr(baseline, name)]
    if candidate.interpretability > baseline.interpretability:
        improvements.append("interpretability")
    cost_ok = (candidate.parameter_count <= baseline.parameter_count * maximum_cost_ratio
               and candidate.runtime_seconds <= baseline.runtime_seconds * maximum_cost_ratio)
    return PromotionDecision(len(improvements) >= 3 and cost_ok, tuple(improvements), cost_ok)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="run a small diagnostic benchmark")
    args = parser.parse_args()
    config = BenchmarkConfig(trajectories=16, steps=12, pretrain_epochs=1, finetune_epochs=2) if args.quick else BenchmarkConfig()
    results = run_benchmark(config)
    print(json.dumps({name: asdict(metrics) for name, metrics in results.items()}, indent=2))
    print(json.dumps(asdict(promotion_decision(results)), indent=2))


if __name__ == "__main__":
    main()
