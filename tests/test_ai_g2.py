from __future__ import annotations

import torch

from fermion.ai_g1.ai_g2 import (AIG2Config, binary_auroc, expected_calibration_error,
                                  load_ai_g2_checkpoint, matched_baseline_report,
                                  run_ai_g2, save_ai_g2_checkpoint, write_manifest)
from fermion.ai_g1.core import MultimodalSpectralGeneralist


def test_auroc_and_calibration_metrics_have_known_sane_values():
    assert binary_auroc(torch.tensor([0.1, 0.2, 0.8, 0.9]), torch.tensor([0, 0, 1, 1])) == 1.0
    probabilities = torch.tensor([[0.9, 0.1], [0.2, 0.8]])
    assert expected_calibration_error(probabilities, torch.tensor([0, 1])) < 0.21


def test_ai_g2_checkpoint_load_is_exact(tmp_path):
    config = AIG2Config(samples=12, train_steps=1, sequential_steps=1)
    model = MultimodalSpectralGeneralist({"numeric": 4, "image": 64}, token_dim=config.token_dim, modes=config.modes,
                                         reconstruction_dim=64)
    inputs = {"numeric": torch.randn(2, 4), "image": torch.randn(2, 64)}
    modes = torch.linspace(0, 1, 8).repeat(2, 1)
    expected = model(inputs, modes).classification.detach()
    path = tmp_path / "ai-g2.pt"; save_ai_g2_checkpoint(path, model, config)
    restored = MultimodalSpectralGeneralist({"numeric": 4, "image": 64}, token_dim=config.token_dim, modes=config.modes,
                                            reconstruction_dim=64)
    load_ai_g2_checkpoint(path, restored, config)
    assert torch.equal(expected, restored(inputs, modes).classification)


def test_matched_baseline_budget_and_three_seed_benchmark_manifest(tmp_path):
    config = AIG2Config(samples=24, train_steps=5, sequential_steps=5)
    report = run_ai_g2(config)
    assert len(report["results"]) == 3 and len(report["sha256"]) == 64
    assert all(item["forgetting"] <= config.forgetting_tolerance for item in report["results"])
    assert all(0.0 <= item["ood_auroc"] <= 1.0 for item in report["results"])
    assert all(item["stochastic_mean_abs_delta"] > 0.0 for item in report["results"])
    path = write_manifest(tmp_path / "manifest.json", report)
    assert path.exists() and report["sha256"] in path.read_text(encoding="utf-8")
    model = MultimodalSpectralGeneralist({"numeric": 4, "image": 64}, token_dim=16, reconstruction_dim=64)
    assert matched_baseline_report(model)["max_to_min_ratio"] < 2.0
