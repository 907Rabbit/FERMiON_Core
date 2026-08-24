"""Phase 17C.5 bounded, evidence-driven curriculum for acquiring program skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .application import Action, ApplicationInterface, CapabilitySet
from .diagnostic_transition import DiagnosticTransitionLayer, EpisodeStep, StateVector
from .skill_acquisition import (HierarchicalSkillPlanner, PlanDecision, SkillExtractor,
                                SkillMemory, SkillValidationReport, SkillValidator)
from .skills import Skill


@dataclass(frozen=True)
class LearningGoal:
    name: str
    required_operations: tuple[str, ...]


@dataclass(frozen=True)
class GoalAnalysis:
    goal: LearningGoal
    plan: PlanDecision
    missing_operations: tuple[str, ...]
    safe_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ExperimentProposal:
    action: Action | None
    risk: float
    requires_approval: bool
    reason: str


@dataclass(frozen=True)
class CurriculumMetrics:
    tasks_attempted: int
    tasks_completed: int
    primitive_actions: int
    reused_skills: int
    new_experiments: int
    failures: int
    approval_requests: int


class LearningManager:
    """Finds skill gaps and conducts only explicitly templated reversible experiments."""

    def __init__(self, layer: DiagnosticTransitionLayer, skill_memory: SkillMemory,
                 experiment_templates: dict[str, Action], *, experiment_risk: float = 0.1,
                 promotion_factory: Callable[[], ApplicationInterface] | None = None):
        self.layer, self.skill_memory = layer, skill_memory
        self.templates, self.experiment_risk = dict(experiment_templates), experiment_risk
        self.promotion_factory = promotion_factory
        self._evidence: dict[str, list[list[EpisodeStep]]] = {}
        self._primitive_actions = self._new_experiments = self._failures = self._approvals = self._reused = 0

    @staticmethod
    def _skill_operations(skill: Skill) -> set[str]:
        return {step.action.get("operation", "") for step in skill.steps}

    def analyze_goal(self, goal: LearningGoal, state: StateVector, capabilities: CapabilitySet) -> GoalAnalysis:
        skills = self.skill_memory.all()
        plan = HierarchicalSkillPlanner().choose(goal.name, state, skills)
        covered = set().union(*(self._skill_operations(skill) for skill in skills if skill.applicable(state))) if skills else set()
        missing = tuple(operation for operation in goal.required_operations if operation not in covered)
        safe = tuple(item.name for item in capabilities.items if item.reversible and item.name in missing)
        if not missing and plan.mode != "known_skill":
            plan = PlanDecision("compose_skills", tuple(skill for skill in skills if skill.applicable(state)),
                                "applicable skills cover required operations")
        return GoalAnalysis(goal, plan, missing, safe)

    def identify_skill_gap(self, analysis: GoalAnalysis) -> tuple[str, ...]:
        return analysis.missing_operations

    def propose_experiment(self, gap: tuple[str, ...], capabilities: CapabilitySet,
                           risk_budget: float) -> ExperimentProposal:
        for operation in gap:
            capability = capabilities.get(operation)
            template = self.templates.get(operation)
            if capability and capability.reversible and template and self.experiment_risk <= risk_budget:
                return ExperimentProposal(template, self.experiment_risk, False, "bounded reversible capability experiment")
        self._approvals += 1
        return ExperimentProposal(None, 0.0, True, "no declared reversible experiment fits the risk budget")

    def execute_experiment(self, proposal: ExperimentProposal) -> EpisodeStep | None:
        if proposal.requires_approval or proposal.action is None:
            return None
        checkpoint = self.layer.checkpoint()
        step = self.layer.step(proposal.action)
        self._primitive_actions += 1; self._new_experiments += 1
        if not step.result.success:
            self._failures += 1
            self.layer.rollback(checkpoint)  # Failed evidence remains in episodic memory.
        return step

    def learn_from_result(self, goal: LearningGoal, episode: list[EpisodeStep]) -> Skill | None:
        if not episode or not all(step.result.success for step in episode):
            return None
        evidence = self._evidence.setdefault(goal.name, [])
        evidence.append(episode)
        if len(evidence) < 2:
            return None
        candidate = SkillExtractor().extract(goal.name, evidence[-2:])
        if self.promotion_factory is None:
            return candidate
        variations = [{key: value["examples"][0] for key, value in candidate.parameters.items()}]
        report = SkillValidator().validate(candidate, self.promotion_factory, variations)
        return candidate if self.skill_memory.promote(candidate, report) else None

    def reassess(self, goal: LearningGoal, state: StateVector, capabilities: CapabilitySet) -> GoalAnalysis:
        return self.analyze_goal(goal, state, capabilities)

    def metrics(self, tasks_attempted: int, tasks_completed: int) -> CurriculumMetrics:
        return CurriculumMetrics(tasks_attempted, tasks_completed, self._primitive_actions, self._reused,
                                 self._new_experiments, self._failures, self._approvals)


@dataclass(frozen=True)
class CurriculumTask:
    goal: LearningGoal
    repetitions: int = 2


class DummyProgramLearningCurriculum:
    """Controlled acquisition benchmark before a live editor integration is permitted."""

    LEVELS = (
        CurriculumTask(LearningGoal("inspect", ("increment",))),
        CurriculumTask(LearningGoal("create_actor", ("create_object",))),
        CurriculumTask(LearningGoal("place_actor", ("create_object", "set_property"))),
    )

    def run(self, manager: LearningManager, tasks: tuple[CurriculumTask, ...] | None = None,
            risk_budget: float = 0.2) -> CurriculumMetrics:
        tasks = tasks or self.LEVELS; completed = 0
        for task in tasks:
            episodes: list[EpisodeStep] = []
            for _ in range(task.repetitions):
                state = manager.layer.encoder.encode(manager.layer.application.observe())
                analysis = manager.analyze_goal(task.goal, state, manager.layer.application.capabilities())
                proposal = manager.propose_experiment(analysis.missing_operations,
                                                      manager.layer.application.capabilities(), risk_budget)
                step = manager.execute_experiment(proposal)
                if step is not None:
                    episodes.append(step)
                    manager.learn_from_result(task.goal, [step])
            if len(episodes) == task.repetitions:
                completed += 1
        return manager.metrics(len(tasks), completed)
