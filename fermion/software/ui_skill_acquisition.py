"""Phase 17C.9 evidence gate for skills acquired through a verified UI backend."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from statistics import mean, pstdev
from typing import Callable

from fermion.adapters.notepad_ui import ProgramLearningMetrics

from .diagnostic_transition import EpisodeStep
from .skill_acquisition import SkillExtractor, SkillMemory, SkillValidationReport
from .skills import Skill


@dataclass(frozen=True)
class UISkillPromotionRequirements:
    minimum_successful_episodes: int = 3
    minimum_distinct_documents: int = 2
    minimum_parameter_variations: int = 2
    required_validation_success_rate: float = 1.0


@dataclass(frozen=True)
class UIEpisodeEvidence:
    goal: str
    document: str
    parameters: dict[str, object]
    steps: tuple[EpisodeStep, ...]
    oracle_verified: bool
    oracle_disagreement: bool
    backend: str = "windows_ui"


class AutonomousUISkillAcquirer:
    """Promotes only repeated, oracle-verified primitive UI trajectories."""

    def __init__(self, memory: SkillMemory, requirements: UISkillPromotionRequirements | None = None):
        self.memory, self.requirements = memory, requirements or UISkillPromotionRequirements()
        self._evidence: dict[str, list[UIEpisodeEvidence]] = {}

    def record_episode(self, evidence: UIEpisodeEvidence) -> bool:
        valid = bool(evidence.steps) and evidence.oracle_verified and not evidence.oracle_disagreement
        valid = valid and all(step.result.success and not step.diagnostic.failure_suspected for step in evidence.steps)
        if valid:
            self._evidence.setdefault(evidence.goal, []).append(evidence)
        return valid

    def candidate(self, goal: str) -> Skill | None:
        evidence = self._evidence.get(goal, [])
        requirement = self.requirements
        if len(evidence) < requirement.minimum_successful_episodes:
            return None
        if len({item.document for item in evidence}) < requirement.minimum_distinct_documents:
            return None
        parameter_values = {json.dumps(item.parameters, sort_keys=True) for item in evidence}
        if len(parameter_values) < requirement.minimum_parameter_variations:
            return None
        skill = SkillExtractor().extract(goal, [list(item.steps) for item in evidence])
        return replace(skill, source="ui_episode", backend_provenance={"application": "notepad",
                       "backend": "windows_ui", "verification": "document_oracle"})

    def promote(self, goal: str, validation: SkillValidationReport) -> Skill | None:
        skill = self.candidate(goal)
        if skill is None or validation.success_rate < self.requirements.required_validation_success_rate:
            return None
        return skill if self.memory.promote(skill, validation, minimum_success_rate=self.requirements.required_validation_success_rate) else None


@dataclass(frozen=True)
class AblationSummary:
    runs: int
    means: dict[str, float]
    standard_deviations: dict[str, float]


class GSENullPrincipleAblation:
    """Runs matched seeded experiments; it reports measurements, not a claimed advantage."""

    def run(self, seeds: tuple[int, ...], experiment: Callable[[int, bool], ProgramLearningMetrics]) -> dict[str, AblationSummary]:
        output = {}
        fields = tuple(ProgramLearningMetrics.__dataclass_fields__)
        for name, enabled in (("gse", True), ("baseline", False)):
            rows = [experiment(seed, enabled) for seed in seeds]
            output[name] = AblationSummary(len(rows), {field: mean(getattr(row, field) for row in rows) for field in fields},
                                            {field: pstdev(getattr(row, field) for row in rows) for field in fields})
        return output
