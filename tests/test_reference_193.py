from __future__ import annotations

import pytest
import torch
from torch.nn import functional as F

from fermion.hr.reference_193 import FermionHR193, PARAMETER_ORDER, reference_inputs

DTYPE = torch.float64


def test_01_parameter_count_and_order():
    model = FermionHR193()
    assert model.parameter_count == 193
    assert tuple(dict(model.named_parameters())) == PARAMETER_ORDER


def test_02_exactly_three_shared_refinements():
    model = FermionHR193()
    trace = model(*reference_inputs())
    assert len(trace.hidden) == 4 and len(trace.gates) == 3
    assert sum(name == "W_r" for name, _ in model.named_parameters()) == 1


def test_03_cpu_output_is_bitwise_deterministic():
    model = FermionHR193()
    first = model(*reference_inputs()).logits.detach()
    second = model(*reference_inputs()).logits.detach()
    assert torch.equal(first, second)


def test_04_checkpoint_round_trip(tmp_path):
    model = FermionHR193()
    _, psi, memory = reference_inputs()
    path = tmp_path / "reference.pt"
    model.save_checkpoint(path, psi, memory)
    restored, restored_psi, restored_memory = FermionHR193.load_checkpoint(path)
    assert torch.equal(psi, restored_psi) and torch.equal(memory, restored_memory)
    for left, right in zip(model.parameters(), restored.parameters()):
        assert torch.equal(left, right)
    assert torch.equal(model(*reference_inputs()).logits, restored(*reference_inputs()).logits)


def test_05_gradients_reach_encoder_through_refinement():
    model = FermionHR193()
    trace = model(*reference_inputs())
    trace.logits.square().sum().backward()
    assert model.W_e.grad is not None
    assert torch.count_nonzero(model.W_e.grad) == model.W_e.numel()
    assert model.W_r.grad is not None and model.W_r.grad.abs().sum() > 0


def test_06_training_changes_values_not_layout():
    model = FermionHR193()
    before_names = tuple(dict(model.named_parameters()))
    before = model.W_e.detach().clone()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.05)
    loss = F.binary_cross_entropy(model(*reference_inputs()).success, torch.ones(1, dtype=DTYPE))
    optimizer.zero_grad(); loss.backward(); optimizer.step()
    assert not torch.equal(before, model.W_e)
    assert tuple(dict(model.named_parameters())) == before_names
    assert model.parameter_count == 193


def test_07_memory_waits_for_validator_evidence():
    model = FermionHR193()
    x, psi, memory = reference_inputs()
    trace = model(x, psi, memory)
    validator = torch.tensor([[1.0, 0.0]], dtype=DTYPE)
    _, updated, _ = model.update_from_state(psi, trace, trace.encoded, validator, memory,
                                             torch.tensor([1.0], dtype=DTYPE))
    assert torch.equal(updated, memory)


def test_08_unreliable_validator_prevents_psi_update():
    model = FermionHR193()
    x, psi, memory = reference_inputs()
    trace = model(x, psi, memory)
    validator = torch.tensor([[0.0, 0.0]], dtype=DTYPE)
    updated, _, eta = model.update_from_state(psi, trace, trace.encoded, validator, memory,
                                               torch.tensor([0.5], dtype=DTYPE))
    assert torch.equal(updated, psi)
    assert torch.equal(eta, torch.zeros_like(eta))


def test_09_energy_terms_sum_to_total():
    model = FermionHR193()
    x, psi, memory = reference_inputs()
    trace = model(x, psi, memory)
    validator = torch.tensor([[1.0, 1.0]], dtype=DTYPE)
    psi_next, memory_next, _ = model.update_from_state(
        psi, trace, trace.encoded, validator, memory, torch.tensor([0.3], dtype=DTYPE))
    report = model.energy(trace, psi_next, memory_next, validator[:, 0], torch.tensor([0.2], dtype=DTYPE))
    terms = report[:-1]
    expected = sum(w * term for w, term in zip(model.config.energy_weights, terms))
    assert torch.equal(expected, report.total)


def test_10_frozen_reference_tensors():
    trace = FermionHR193()(*reference_inputs())
    expected_encoded = torch.tensor([[-0.12523560360845282, -0.14756563408577453,
                                      -0.27202769357355011, 0.03133721612961272]], dtype=DTYPE)
    expected_hidden = torch.tensor([[-0.08860022418964300, 0.06940050371961548,
                                     -0.22092733857752062, -0.07705060933261397]], dtype=DTYPE)
    expected_logits = torch.tensor([[-0.09303226300117971, 0.21233344458475356]], dtype=DTYPE)
    assert torch.allclose(trace.encoded, expected_encoded, rtol=0.0, atol=1e-15)
    assert torch.allclose(trace.hidden[3], expected_hidden, rtol=0.0, atol=1e-15)
    assert torch.allclose(trace.logits, expected_logits, rtol=0.0, atol=1e-15)


def test_11_incompatible_checkpoint_fails_loudly(tmp_path):
    path = tmp_path / "bad.pt"
    torch.save({"format": 999, "parameter_order": PARAMETER_ORDER}, path)
    with pytest.raises(ValueError, match="incompatible"):
        FermionHR193.load_checkpoint(path)


def test_12_three_steps_can_learn_reference_mapping_at_least_as_well_as_zero():
    # Optimize two clones on the same deterministic mapping. This is an ablation
    # smoke test; the full curriculum supplies statistically powered comparisons.
    x, psi, memory = reference_inputs()
    target = torch.ones(1, dtype=DTYPE)
    losses = []
    for steps in (0, 3):
        model = FermionHR193()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
        for _ in range(80):
            loss = F.binary_cross_entropy(model(x, psi, memory, steps=steps).success, target)
            optimizer.zero_grad(); loss.backward(); optimizer.step()
        losses.append(F.binary_cross_entropy(model(x, psi, memory, steps=steps).success, target).item())
    assert losses[1] <= losses[0] + 1e-4


def test_13_training_reduces_heldout_outcome_loss():
    model = FermionHR193()
    train_x = torch.tensor([[0.8, 0.5, -0.4, 0.3], [-0.8, -0.5, 0.4, -0.3]], dtype=DTYPE)
    train_y = torch.tensor([1.0, 0.0], dtype=DTYPE)
    held_x = torch.tensor([[0.7, 0.4, -0.3, 0.2], [-0.7, -0.4, 0.3, -0.2]], dtype=DTYPE)
    held_y = train_y.clone()
    psi = torch.zeros((2, 3), dtype=DTYPE); memory = torch.zeros((2, 3), dtype=DTYPE)
    before = F.binary_cross_entropy(model(held_x, psi, memory).success, held_y).item()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.02)
    for _ in range(120):
        loss = F.binary_cross_entropy(model(train_x, psi, memory).success, train_y)
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    after = F.binary_cross_entropy(model(held_x, psi, memory).success, held_y).item()
    assert after < before


def test_14_outputs_are_finite_under_extreme_inputs():
    model = FermionHR193()
    for magnitude in (-1e12, 1e12):
        trace = model(torch.full((2, 4), magnitude, dtype=DTYPE),
                      torch.full((2, 3), magnitude, dtype=DTYPE),
                      torch.full((2, 3), magnitude, dtype=DTYPE))
        assert all(torch.isfinite(tensor).all() for tensor in (trace.encoded, trace.logits,
                                                               trace.success, trace.effect_energy))


def test_15_finite_difference_gradient_agrees():
    model = FermionHR193()
    x, psi, memory = reference_inputs()
    loss = model(x, psi, memory).logits.sum()
    loss.backward()
    analytic = model.W_e.grad[0, 0].item()
    epsilon = 1e-6
    with torch.no_grad():
        original = model.W_e[0, 0].item()
        model.W_e[0, 0] = original + epsilon
        plus = model(x, psi, memory).logits.sum().item()
        model.W_e[0, 0] = original - epsilon
        minus = model(x, psi, memory).logits.sum().item()
        model.W_e[0, 0] = original
    numeric = (plus - minus) / (2 * epsilon)
    relative = abs(analytic - numeric) / max(1.0, abs(analytic), abs(numeric))
    assert relative < 1e-4
