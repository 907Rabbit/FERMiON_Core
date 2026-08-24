"""Reproducible AI-G2 continual-multimodal benchmark harness.

The benchmark uses synthetic data intentionally: it tests measurement plumbing,
comparative ablations, retention, and uncertainty before claiming real-world
generalisation.  It is independent of FERMiON-HR-193 and CP10/CP11.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import torch
from torch import Tensor
from torch.nn import functional as F

from .core import MLPBaseline, MultimodalSpectralGeneralist, ReplayBuffer, TransformerBaseline


@dataclass(frozen=True)
class AIG2Config:
    seeds: tuple[int, int, int] = (101, 211, 307)
    samples: int = 72
    train_steps: int = 28
    sequential_steps: int = 28
    learning_rate: float = 0.015
    token_dim: int = 16
    modes: int = 8
    image_side: int = 8
    forgetting_tolerance: float = 0.05


def parameter_count(model: torch.nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def _closest_baselines(target: int, *, input_dim: int, classes: int, token_dim: int) -> tuple[MLPBaseline, TransformerBaseline]:
    mlp = min((MLPBaseline(input_dim, hidden, classes) for hidden in range(4, 257)),
              key=lambda item: abs(parameter_count(item) - target))
    choices = (8, 10, 12, 14, 16, 18, 20, 24, 28, 32)
    transformer = min((TransformerBaseline(width, classes, heads=2) for width in choices),
                      key=lambda item: abs(parameter_count(item) - target))
    return mlp, transformer


def matched_baseline_report(model: MultimodalSpectralGeneralist) -> dict[str, int | float]:
    target = parameter_count(model)
    input_dim = sum(model.modality_dims.values())
    mlp, transformer = _closest_baselines(target, input_dim=input_dim, classes=model.classification_head.out_features,
                                          token_dim=model.token_dim)
    values = {"spectral_core": target, "mlp": parameter_count(mlp), "transformer": parameter_count(transformer)}
    values["max_to_min_ratio"] = max(values.values()) / min(values.values())
    return values


def binary_auroc(scores: Tensor, labels: Tensor) -> float:
    """Tie-aware AUROC without an sklearn dependency."""
    scores, labels = scores.detach().flatten().double(), labels.detach().flatten().bool()
    positive, negative = int(labels.sum()), int((~labels).sum())
    if positive == 0 or negative == 0:
        raise ValueError("AUROC requires both positive and negative examples")
    order = torch.argsort(scores)
    ordered = scores[order]
    ranks = torch.empty_like(scores)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end] == ordered[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    return float((ranks[labels].sum() - positive * (positive + 1) / 2.0) / (positive * negative))


def expected_calibration_error(probabilities: Tensor, labels: Tensor, bins: int = 10) -> float:
    confidence, predicted = probabilities.max(dim=-1)
    correct = predicted.eq(labels)
    total = confidence.numel()
    ece = torch.zeros((), dtype=confidence.dtype, device=confidence.device)
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (confidence >= lower) & ((confidence < upper) if index < bins - 1 else (confidence <= upper))
        if mask.any():
            ece = ece + mask.float().mean() * (correct[mask].float().mean() - confidence[mask].mean()).abs()
    return float(ece.detach())


def _dataset(config: AIG2Config, seed: int) -> dict[str, Tensor]:
    generator = torch.Generator().manual_seed(seed)
    n, side = config.samples, config.image_side
    numeric = torch.rand(n, 4, generator=generator) * 2 - 1
    grid = torch.linspace(-1, 1, side)
    yy, xx = torch.meshgrid(grid, grid, indexing="ij")
    center = numeric[:, :2].reshape(n, 2, 1, 1)
    image = torch.exp(-7.0 * ((xx - center[:, 0]).square() + (yy - center[:, 1]).square())).reshape(n, side * side)
    classes = ((numeric[:, 0] * numeric[:, 1] + 0.15 * numeric[:, 2]) > 0).long()
    regression = (torch.sin(2.2 * numeric[:, :1]) + numeric[:, 1:2].square() - 0.3 * numeric[:, 2:3])
    base = numeric[:, :1]
    time_series = torch.cat((torch.sin(base + 0.4), torch.sin(base + 0.8), torch.sin(base + 1.2)), dim=-1)
    return {"numeric": numeric, "image": image, "classes": classes, "regression": regression,
            "time_series": time_series, "reconstruction": image}


def _loss(output: Any, data: dict[str, Tensor]) -> Tensor:
    return (F.cross_entropy(output.classification, data["classes"])
            + F.mse_loss(output.regression, data["regression"])
            + F.mse_loss(output.time_series, data["time_series"])
            + F.mse_loss(output.reconstruction, data["reconstruction"]))


def _train_multitask(model: MultimodalSpectralGeneralist, data: dict[str, Tensor], config: AIG2Config) -> None:
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    modes = torch.linspace(0, 2, config.modes).repeat(config.samples, 1)
    inputs = {"numeric": data["numeric"], "image": data["image"]}
    for _ in range(config.train_steps):
        loss = _loss(model(inputs, modes), data)
        optimizer.zero_grad(); loss.backward(); optimizer.step()


def _sequential_retention(model: MultimodalSpectralGeneralist, data: dict[str, Tensor], config: AIG2Config) -> float:
    """Train a new regression phase while replaying task-A class examples."""
    modes = torch.linspace(0, 2, config.modes).repeat(config.samples, 1)
    inputs = {"numeric": data["numeric"], "image": data["image"]}
    before = float((model(inputs, modes).classification.argmax(-1) == data["classes"]).float().mean())
    replay = ReplayBuffer(config.samples)
    for index in range(config.samples):
        replay.append(numeric=data["numeric"][index], image=data["image"][index], classes=data["classes"][index])
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate * 0.5)
    for _ in range(config.sequential_steps):
        replayed = replay.sample(min(32, config.samples))
        replay_modes = torch.linspace(0, 2, config.modes).repeat(replayed["classes"].shape[0], 1)
        output = model({"numeric": data["numeric"], "image": data["image"]}, modes)
        replay_output = model({"numeric": replayed["numeric"], "image": replayed["image"]}, replay_modes)
        loss = F.mse_loss(output.regression, data["regression"]) + F.cross_entropy(replay_output.classification, replayed["classes"])
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    after = float((model(inputs, modes).classification.argmax(-1) == data["classes"]).float().mean())
    return max(0.0, before - after)


def save_ai_g2_checkpoint(path: str | Path, model: MultimodalSpectralGeneralist, config: AIG2Config) -> None:
    torch.save({"format": 1, "architecture": "FERMiON-AI-G2", "config": asdict(config),
                "state_dict": model.state_dict()}, path)


def load_ai_g2_checkpoint(path: str | Path, model: MultimodalSpectralGeneralist, config: AIG2Config) -> None:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if payload.get("format") != 1 or payload.get("architecture") != "FERMiON-AI-G2":
        raise ValueError("incompatible AI-G2 checkpoint")
    if payload.get("config") != asdict(config):
        raise ValueError("AI-G2 checkpoint configuration mismatch")
    model.load_state_dict(payload["state_dict"], strict=True)


def run_ai_g2(config: AIG2Config = AIG2Config()) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for seed in config.seeds:
        torch.manual_seed(seed)
        data = _dataset(config, seed)
        model = MultimodalSpectralGeneralist({"numeric": 4, "image": config.image_side ** 2},
                                             token_dim=config.token_dim, modes=config.modes,
                                             reconstruction_dim=config.image_side ** 2)
        model.set_in_distribution_reference({"numeric": data["numeric"], "image": data["image"]})
        _train_multitask(model, data, config)
        modes = torch.linspace(0, 2, config.modes).repeat(config.samples, 1)
        deterministic = model({"numeric": data["numeric"], "image": data["image"]}, modes, stochastic=False)
        stochastic = model({"numeric": data["numeric"], "image": data["image"]}, modes, stochastic=True)
        # Deliberately remote synthetic inputs, declared here so AUROC is a
        # measurable OOD check rather than a claim about natural-image shift.
        ood = {"numeric": data["numeric"] + 8.0, "image": data["image"] + 8.0}
        ood_score = model(ood, modes).uncertainty.squeeze(-1)
        id_score = deterministic.uncertainty.squeeze(-1)
        scores = torch.cat((id_score, ood_score)); labels = torch.cat((torch.zeros_like(id_score), torch.ones_like(ood_score)))
        forgetting = _sequential_retention(model, data, config)
        ablated = MultimodalSpectralGeneralist({"numeric": 4, "image": config.image_side ** 2}, token_dim=config.token_dim,
                                               modes=config.modes, reconstruction_dim=config.image_side ** 2,
                                               use_spectral_field=False)
        ablated.set_in_distribution_reference({"numeric": data["numeric"], "image": data["image"]})
        _train_multitask(ablated, data, config)
        ablated_loss = float(_loss(ablated({"numeric": data["numeric"], "image": data["image"]}, modes), data).detach())
        results.append({
            "seed": seed,
            "classification_accuracy": float((deterministic.classification.argmax(-1) == data["classes"]).float().mean().detach()),
            "regression_mse": float(F.mse_loss(deterministic.regression, data["regression"]).detach()),
            "time_series_mse": float(F.mse_loss(deterministic.time_series, data["time_series"]).detach()),
            "image_reconstruction_mse": float(F.mse_loss(deterministic.reconstruction, data["reconstruction"]).detach()),
            "forgetting": forgetting,
            "ood_auroc": binary_auroc(scores, labels),
            "calibration_ece": expected_calibration_error(torch.softmax(deterministic.classification, -1), data["classes"]),
            "stochastic_mean_abs_delta": float((stochastic.classification - deterministic.classification).abs().mean().detach()),
            "spectral_ablation_loss": ablated_loss,
            "spectral_loss": float(_loss(deterministic, data).detach()),
        })
    report = {"format": "FERMiON-AI-G2-results-v1", "config": asdict(config), "baseline_budget": matched_baseline_report(model),
              "results": results}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["sha256"] = hashlib.sha256(encoded).hexdigest()
    return report


def write_manifest(path: str | Path, report: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return destination
