from __future__ import annotations

from fermion.hr.memory import EpisodicMemory
from fermion.software.application import Action, DummyApplicationAdapter
from fermion.software.diagnostic_transition import (ApplicationEpisodicMemory, DiagnosticTransitionLayer,
                                                    DummyStateEncoder, DummyTransitionModel, GSEDiagnosticEngine)
from fermion.software.skill_acquisition import (HierarchicalSkillPlanner, SkillExtractor, SkillMemory, SkillValidator)


def episode(tmp_path, amount: int):
    memory = EpisodicMemory(tmp_path / f"{amount}.db")
    layer = DiagnosticTransitionLayer(DummyApplicationAdapter(), DummyStateEncoder(), DummyTransitionModel(),
                                      GSEDiagnosticEngine(), ApplicationEpisodicMemory(memory))
    step = layer.step(Action("increment", {"amount": amount}))
    return [step], memory


def test_extractor_creates_parameterized_skill_from_repeated_episodes(tmp_path):
    first, first_memory = episode(tmp_path, 1); second, second_memory = episode(tmp_path, 2)
    skill = SkillExtractor().extract("increment", [first, second])
    assert skill.parameters["step0_amount"]["required"]
    assert skill.instantiate(step0_amount=4)[0]["arguments"]["amount"] == 4
    first_memory.close(); second_memory.close()


def test_extractor_rejects_failed_trajectories(tmp_path):
    memory = EpisodicMemory(tmp_path / "failed.db")
    layer = DiagnosticTransitionLayer(DummyApplicationAdapter(), DummyStateEncoder(), DummyTransitionModel(),
                                      GSEDiagnosticEngine(), ApplicationEpisodicMemory(memory))
    failed = [layer.step(Action("inject_failure"))]
    import pytest
    with pytest.raises(ValueError, match="successful"):
        SkillExtractor().extract("bad", [failed])
    memory.close()


def test_validator_replays_controlled_variations_and_promotes_evidence(tmp_path):
    first, first_memory = episode(tmp_path, 1); second, second_memory = episode(tmp_path, 2)
    skill = SkillExtractor().extract("increment", [first, second])
    report = SkillValidator().validate(skill, DummyApplicationAdapter, [{"step0_amount": 3}, {"step0_amount": 4}])
    store = SkillMemory(tmp_path / "skills.json")
    assert report.success_rate == 1 and report.mean_execution_cost >= 0
    assert store.promote(skill, report) and store.all()[0].confidence == 1
    first_memory.close(); second_memory.close()


def test_failed_validation_is_not_promoted(tmp_path):
    first, first_memory = episode(tmp_path, 1); second, second_memory = episode(tmp_path, 2)
    skill = SkillExtractor().extract("increment", [first, second])
    report = SkillValidator().validate(skill, DummyApplicationAdapter, [{}])
    assert not SkillMemory(tmp_path / "skills.json").promote(skill, report)
    first_memory.close(); second_memory.close()


def test_planner_selects_known_skill_then_safe_exploration(tmp_path):
    first, first_memory = episode(tmp_path, 1); second, second_memory = episode(tmp_path, 2)
    skill = SkillExtractor().extract("increment", [first, second])
    planner = HierarchicalSkillPlanner()
    assert planner.choose("increment", first[0].state, (skill,)).mode == "known_skill"
    assert planner.choose("unknown", first[0].state, (), allow_safe_exploration=True).mode == "explore_safely"
    first_memory.close(); second_memory.close()


def test_planner_requests_approval_when_no_safe_skill_exists(tmp_path):
    first, memory = episode(tmp_path, 1)
    assert HierarchicalSkillPlanner().choose("unknown", first[0].state, ()).mode == "ask_for_approval"
    memory.close()
