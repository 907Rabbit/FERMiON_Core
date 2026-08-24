from __future__ import annotations

from fermion.adapters.notepad_ui import ProgramLearningMetrics
from fermion.software.application import Action, ActionResult
from fermion.software.diagnostic_transition import (DiagnosticReport, EpisodeStep, StatePrediction, StateVector)
from fermion.software.skill_acquisition import SkillMemory, SkillValidationReport
from fermion.software.ui_skill_acquisition import (AutonomousUISkillAcquirer, GSENullPrincipleAblation,
                                                    UIEpisodeEvidence, UISkillPromotionRequirements)


def episode(text: str, document: str, *, verified=True, disagreement=False, success=True):
    state = StateVector((0.0,), ("counter",))
    diagnostic = DiagnosticReport(0, 0, 0, 0, 1, not success, (), 0, (0, 0, 0, 0), 0, 0)
    steps = tuple(EpisodeStep(str(index), None, "root", float(index), state, Action(operation, arguments),
                              StatePrediction(state, 1, True), state,
                              ActionResult(str(index), success, success), diagnostic)
                  for index, (operation, arguments) in enumerate((
                      ("open_document", {"path": document}), ("type_text", {"text": text}), ("save_document", {}))))
    return UIEpisodeEvidence("append_and_save", document, {"text": text}, steps, verified, disagreement)


def test_ui_skill_requires_three_verified_parameterized_multi_document_episodes(tmp_path):
    acquirer = AutonomousUISkillAcquirer(SkillMemory(tmp_path / "skills.json"))
    assert acquirer.record_episode(episode("A", "one.txt"))
    assert acquirer.record_episode(episode("B", "two.txt"))
    assert acquirer.candidate("append_and_save") is None
    assert acquirer.record_episode(episode("C", "one.txt"))
    skill = acquirer.candidate("append_and_save")
    assert skill and skill.backend_provenance["verification"] == "document_oracle"
    assert [step.action["operation"] for step in skill.steps] == ["open_document", "type_text", "save_document"]


def test_oracle_disagreement_or_ui_failure_cannot_become_procedural_knowledge(tmp_path):
    acquirer = AutonomousUISkillAcquirer(SkillMemory(tmp_path / "skills.json"))
    assert not acquirer.record_episode(episode("A", "one.txt", disagreement=True))
    assert not acquirer.record_episode(episode("A", "one.txt", success=False))
    assert acquirer.candidate("append_and_save") is None


def test_ui_skill_promotion_requires_perfect_validation(tmp_path):
    memory = SkillMemory(tmp_path / "skills.json"); acquirer = AutonomousUISkillAcquirer(memory)
    for text, document in (("A", "one.txt"), ("B", "two.txt"), ("C", "one.txt")):
        acquirer.record_episode(episode(text, document))
    failed = SkillValidationReport(2, 1, 0.5, 0, 0.1, ("oracle disagreement",))
    passed = SkillValidationReport(2, 2, 1, 0, 0.1, ())
    assert acquirer.promote("append_and_save", failed) is None
    assert acquirer.promote("append_and_save", passed) and memory.all()[0].source == "ui_episode"


def test_gse_null_principle_ablation_reports_seeded_means_and_uncertainty():
    def experiment(seed, gse):
        return ProgramLearningMetrics(seed + int(gse), seed, 0, 0, 0, 1, 1, 1)
    report = GSENullPrincipleAblation().run((1, 2, 3), experiment)
    assert report["gse"].runs == 3 and report["gse"].means["task_success"] == 3
    assert report["baseline"].standard_deviations["task_success"] > 0
