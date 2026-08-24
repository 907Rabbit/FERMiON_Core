from __future__ import annotations

import pytest
import torch

from fermion.hr.checkpoint import load_checkpoint, save_checkpoint
from fermion.hr.config import HRConfig
from fermion.hr.contracts import CandidateProgram, ValidatorEvidence
from fermion.hr.encoders import MultimodalEncoder
from fermion.hr.system import FermionHR


def observations(config: HRConfig, batch: int = 2):
    return {name: torch.randn(batch, dimension) for name, dimension in config.modality_dims.items()}


def test_multimodal_encoder_distinguishes_missing_channels():
    config = HRConfig()
    encoder = MultimodalEncoder(config)
    values = observations(config)
    values["vision"] = None
    encoded, availability = encoder(values)
    assert encoded.shape == (2, config.encoded_dim)
    assert availability.shape == (2, len(config.modality_dims))
    assert torch.equal(availability[:, 1], torch.zeros(2))


def test_integrated_controller_routes_predicts_and_reports_energy():
    config = HRConfig()
    model = FermionHR(config)
    state = model.initial_state(2)
    candidates = torch.randn(2, 3, config.candidate_dim)
    decision = model(observations(config), state, candidates)
    assert decision.selected_index.shape == (2,)
    assert decision.predicted_next.shape == (2, config.encoded_dim)
    assert set(decision.energy.named()) == {"state", "prediction", "goal", "memory",
                                             "uncertainty", "cost", "stability", "total"}


def test_state_update_is_hard_gated_by_validator_information():
    config = HRConfig()
    model = FermionHR(config)
    state = model.initial_state()
    values = {name: value[:1] for name, value in observations(config).items()}
    decision = model(values, state, torch.randn(1, 2, config.candidate_dim))
    unchanged = model.update_state(state, decision, values, ValidatorEvidence(1, 0))
    assert torch.equal(unchanged.psi, state.psi) and torch.equal(unchanged.memory, state.memory)
    changed = model.update_state(state, decision, values, ValidatorEvidence(1, 1))
    assert not torch.equal(changed.psi, state.psi)


def test_production_checkpoint_round_trip_and_config_guard(tmp_path):
    config = HRConfig(); model = FermionHR(config); state = model.initial_state()
    path = tmp_path / "hr.pt"; save_checkpoint(path, model, config, state.psi, state.memory)
    restored = FermionHR(config)
    psi, memory, _ = load_checkpoint(path, restored, config)
    assert torch.equal(psi, state.psi) and torch.equal(memory, state.memory)
    for left, right in zip(model.parameters(), restored.parameters()):
        assert torch.equal(left, right)
    incompatible = HRConfig(hidden_dim=16)
    with pytest.raises(ValueError, match="configuration"):
        load_checkpoint(path, FermionHR(incompatible), incompatible)


def test_candidate_contract_features_are_fixed_width():
    model = FermionHR()
    candidates = [CandidateProgram("a", "pass", features=(1, 2), estimated_risk=0.3),
                  CandidateProgram("b", "pass", features=tuple(range(100)))]
    features = model.candidate_features(candidates)
    assert features.shape == (1, 2, model.config.candidate_dim)
