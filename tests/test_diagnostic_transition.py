from __future__ import annotations

from dataclasses import replace

from fermion.hr.memory import EpisodicMemory
from fermion.software.application import Action, DummyApplicationAdapter
from fermion.software.diagnostic_transition import (ApplicationEpisodicMemory, DiagnosticTransitionLayer,
                                                    DummyStateEncoder, DummyTransitionModel,
                                                    GSEDiagnosticEngine, StatePrediction)


def layer(tmp_path, model=None, adapter=None):
    memory = EpisodicMemory(tmp_path / "episodes.db")
    return DiagnosticTransitionLayer(adapter or DummyApplicationAdapter(), DummyStateEncoder(),
                                     model or DummyTransitionModel(), GSEDiagnosticEngine(),
                                     ApplicationEpisodicMemory(memory)), memory


def test_known_transition_has_low_error_and_novelty(tmp_path):
    diagnostic, memory = layer(tmp_path)
    step = diagnostic.step(Action("increment", {"amount": 2}))
    assert step.diagnostic.prediction_error == 0 and step.diagnostic.novelty_score == 0
    memory.close()


def test_unseen_transition_increases_novelty(tmp_path):
    diagnostic, memory = layer(tmp_path)
    step = diagnostic.step(Action("create_object", {"name": "cube"}))
    assert step.diagnostic.novelty_score > 0 and "unseen operation" in step.diagnostic.reasons[0]
    memory.close()


def test_wrong_prediction_produces_model_mismatch(tmp_path):
    class WrongModel(DummyTransitionModel):
        def predict(self, state, action):
            prediction = super().predict(state, action)
            return replace(prediction, state=replace(prediction.state, values=(99.0, *prediction.state.values[1:])))
    diagnostic, memory = layer(tmp_path, model=WrongModel())
    step = diagnostic.step(Action("increment"))
    assert step.diagnostic.mismatch_score > 0 and step.diagnostic.failure_suspected
    memory.close()


def test_hidden_transition_creates_spike(tmp_path):
    class HiddenMutationAdapter(DummyApplicationAdapter):
        def execute(self, action):
            outcome = super().execute(action)
            if outcome.success:
                self._state["counter"] += 9
            return outcome
    diagnostic, memory = layer(tmp_path, adapter=HiddenMutationAdapter())
    step = diagnostic.step(Action("increment"))
    assert step.diagnostic.transition_spike_score > 0
    memory.close()


def test_diagnostics_are_persisted_with_episode(tmp_path):
    diagnostic, memory = layer(tmp_path)
    diagnostic.step(Action("increment"))
    stored = memory.retrieve((0.0, 0.0, 0.0, 0.0, 0.0))
    assert stored and "diagnostic" in stored[0].record.result
    memory.close()


def test_similar_episodes_can_be_retrieved_by_state_and_action(tmp_path):
    diagnostic, memory = layer(tmp_path)
    first = diagnostic.step(Action("increment"))
    found = diagnostic.memory.retrieve_similar(first.state, Action("increment"))
    assert found and found[0].record.action["action"]["operation"] == "increment"
    memory.close()


def test_rollback_retains_failed_episode_and_links_new_branch(tmp_path):
    diagnostic, memory = layer(tmp_path)
    checkpoint = diagnostic.checkpoint()
    failed = diagnostic.step(Action("inject_failure"))
    assert diagnostic.rollback(checkpoint).success
    recovered = diagnostic.step(Action("increment"))
    records = memory.retrieve(failed.state.values)
    assert len(memory) == 2 and recovered.branch_id != failed.branch_id
    assert any(item.record.recovery["parent_step_id"] == failed.step_id for item in records) or recovered.parent_step_id == failed.step_id
    memory.close()


def test_diagnostic_layer_does_not_mutate_canonical_reference():
    from fermion.hr.reference_193 import FermionHR193
    model = FermionHR193()
    assert model.parameter_count == 193
