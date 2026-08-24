from __future__ import annotations

from fermion.hr.memory import EpisodicMemory
from fermion.software.application import Action, DummyApplicationAdapter
from fermion.software.diagnostic_transition import (ApplicationEpisodicMemory, DiagnosticTransitionLayer,
                                                    DummyStateEncoder, DummyTransitionModel, GSEDiagnosticEngine)
from fermion.software.learning_manager import CurriculumTask, DummyProgramLearningCurriculum, LearningGoal, LearningManager
from fermion.software.skill_acquisition import SkillMemory


def manager(tmp_path):
    adapter = DummyApplicationAdapter()
    layer = DiagnosticTransitionLayer(adapter, DummyStateEncoder(), DummyTransitionModel(), GSEDiagnosticEngine(),
                                      ApplicationEpisodicMemory(EpisodicMemory(tmp_path / "episodes.db")))
    return LearningManager(layer, SkillMemory(tmp_path / "skills.json"),
                           {"increment": Action("increment", {"amount": 1}),
                            "create_object": Action("create_object", {"name": "cube"})},
                           promotion_factory=DummyApplicationAdapter)


def test_goal_analysis_identifies_missing_declared_capability(tmp_path):
    learning = manager(tmp_path)
    state = learning.layer.encoder.encode(learning.layer.application.observe())
    result = learning.analyze_goal(LearningGoal("increment", ("increment",)), state,
                                   learning.layer.application.capabilities())
    assert result.missing_operations == ("increment",) and result.safe_capabilities == ("increment",)


def test_experiment_is_bounded_by_risk_and_reversibility(tmp_path):
    learning = manager(tmp_path); capabilities = learning.layer.application.capabilities()
    denied = learning.propose_experiment(("increment",), capabilities, 0.01)
    allowed = learning.propose_experiment(("increment",), capabilities, 0.2)
    assert denied.requires_approval and allowed.action and allowed.action.operation == "increment"


def test_experiment_executes_only_declared_template_and_records_episode(tmp_path):
    learning = manager(tmp_path)
    proposal = learning.propose_experiment(("increment",), learning.layer.application.capabilities(), 0.2)
    step = learning.execute_experiment(proposal)
    assert step and step.result.success and len(learning.layer.memory.memory) == 1


def test_repeated_evidence_promotes_validated_skill(tmp_path):
    learning = manager(tmp_path); goal = LearningGoal("increment", ("increment",))
    proposal = learning.propose_experiment(("increment",), learning.layer.application.capabilities(), 0.2)
    first = learning.execute_experiment(proposal)
    second = learning.execute_experiment(proposal)
    assert first and second and learning.learn_from_result(goal, [first]) is None
    skill = learning.learn_from_result(goal, [second])
    assert skill and learning.skill_memory.all()[0].name == "increment"


def test_failure_is_retained_and_triggers_rollback_branch(tmp_path):
    learning = manager(tmp_path)
    proposal = type("Proposal", (), {"requires_approval": False, "action": Action("inject_failure")})()
    step = learning.execute_experiment(proposal)
    assert step and not step.result.success and len(learning.layer.memory.memory) == 1


def test_reassessment_uses_promoted_skills_and_canonical_core_is_untouched(tmp_path):
    learning = manager(tmp_path); goal = LearningGoal("increment", ("increment",))
    proposal = learning.propose_experiment(("increment",), learning.layer.application.capabilities(), 0.2)
    first = learning.execute_experiment(proposal); second = learning.execute_experiment(proposal)
    learning.learn_from_result(goal, [first]); learning.learn_from_result(goal, [second])
    state = learning.layer.encoder.encode(learning.layer.application.observe())
    assert learning.reassess(goal, state, learning.layer.application.capabilities()).plan.mode in {"known_skill", "compose_skills"}
    from fermion.hr.reference_193 import FermionHR193
    assert FermionHR193().parameter_count == 193


def test_dummy_curriculum_promotes_skill_after_repeated_bounded_experiments(tmp_path):
    learning = manager(tmp_path)
    report = DummyProgramLearningCurriculum().run(
        learning, (CurriculumTask(LearningGoal("increment", ("increment",))),))
    assert report.tasks_completed == 1 and report.new_experiments == 2
    assert learning.skill_memory.all()[0].name == "increment"
