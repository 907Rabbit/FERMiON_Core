from __future__ import annotations

from fermion.adapters.notepad import NotepadConfig, NotepadSandboxAdapter
from fermion.adapters.notepad_ui import (ClosedLoopNotepadAdapter, NotepadUIAdapter, ProgramLearningMetrics,
                                         PywinautoNotepadController, compare_gse_ablation)
from fermion.software.application import Action, ActionResult
from fermion.hr.memory import EpisodicMemory
from fermion.software.diagnostic_transition import (ApplicationEpisodicMemory, DiagnosticTransitionLayer,
                                                    DummyStateEncoder, DummyTransitionModel, GSEDiagnosticEngine)


class FakeUIController:
    def __init__(self, result: ActionResult | None = None):
        self.result = result
        self.actions: list[Action] = []

    def observe(self):
        return {"title": "sample.txt - Notepad", "visible": True, "backend": "accessibility"}

    def perform(self, action):
        self.actions.append(action)
        return self.result or ActionResult(action.action_id, True, True, {"belief": "saved"})


def closed_loop(tmp_path, controller=None):
    oracle = NotepadSandboxAdapter(NotepadConfig(tmp_path / "FERMiON_Sandbox"))
    return ClosedLoopNotepadAdapter(NotepadUIAdapter(controller or FakeUIController()), oracle), oracle


def test_closed_loop_combines_accessibility_and_document_oracle_observations(tmp_path):
    adapter, _ = closed_loop(tmp_path)
    observation = adapter.observe()
    assert observation.state["ui"]["backend"] == "accessibility"
    assert observation.channels["document_oracle"]


def test_ui_success_is_rejected_when_oracle_does_not_observe_expected_effect(tmp_path):
    adapter, _ = closed_loop(tmp_path)
    result = adapter.execute(Action("type_text", {"text": "hello"}))
    verification = adapter.verify(result, {"documents": {"sample.txt": "hello"}})
    assert result.success and not verification.success
    assert verification.observed_effect["comparison"]["disagreement"]


def test_ui_and_oracle_can_agree_on_durable_document_effect(tmp_path):
    adapter, oracle = closed_loop(tmp_path)
    result = adapter.execute(Action("type_text", {"text": "hello"}))
    oracle.execute(Action("create_document", {"name": "sample.txt", "content": "hello"}))
    verification = adapter.verify(result, {"documents": {"sample.txt": "hello"}})
    assert verification.success and not verification.observed_effect["comparison"]["disagreement"]


def test_ui_adapter_exposes_only_small_safe_action_surface(tmp_path):
    adapter, _ = closed_loop(tmp_path)
    assert not adapter.execute(Action("delete_document", {"name": "sample.txt"})).success
    assert {item.name for item in adapter.capabilities().items} == {"open_document", "move_cursor_end", "type_text", "save_document", "select_all", "undo", "close_without_saving"}


def test_closed_loop_uses_oracle_for_exact_checkpoint_and_rollback(tmp_path):
    adapter, oracle = closed_loop(tmp_path); checkpoint = adapter.checkpoint()
    oracle.execute(Action("create_document", {"name": "sample.txt", "content": "x"}))
    assert adapter.rollback(checkpoint).success and oracle.observe().state == {"documents": {}}


def test_gse_ablation_rows_are_metric_aligned():
    gse = ProgramLearningMetrics(1, 2, 3, 4, 5, 6, 7, 8)
    baseline = ProgramLearningMetrics(8, 7, 6, 5, 4, 3, 2, 1)
    assert compare_gse_ablation(gse, baseline)["failed_actions"] == (3, 6)


def test_real_controller_refuses_a_non_sandbox_document_before_launch(tmp_path):
    pytest = __import__("pytest"); pytest.importorskip("pywinauto")
    sandbox = tmp_path / "FERMiON_Sandbox"; sandbox.mkdir()
    controller = PywinautoNotepadController(sandbox)
    result = controller.perform(Action("open_document", {"path": str(tmp_path / "outside.txt")}))
    assert not result.success and "direct .txt file" in result.error


def test_structured_target_failures_are_retryable_evidence(tmp_path):
    sandbox = tmp_path / "FERMiON_Sandbox"; sandbox.mkdir()
    controller = PywinautoNotepadController(sandbox)
    result = controller.perform(Action("type_text", {"text": "x"}))
    assert not result.success and result.details["reason"] == "target_not_open" and result.details["retryable"]


def test_ui_target_failure_is_retained_as_diagnostic_episode(tmp_path):
    failed = ActionResult("fixed", False, False, {"reason": "target_control_not_found", "retryable": True}, "target_control_not_found")
    adapter, _ = closed_loop(tmp_path, FakeUIController(failed))
    memory = EpisodicMemory(tmp_path / "episodes.db")
    layer = DiagnosticTransitionLayer(adapter, DummyStateEncoder(), DummyTransitionModel(), GSEDiagnosticEngine(),
                                      ApplicationEpisodicMemory(memory))
    step = layer.step(Action("type_text", {"text": "x"}))
    assert not step.result.success and step.diagnostic.failure_suspected and len(memory) == 1
    memory.close()
