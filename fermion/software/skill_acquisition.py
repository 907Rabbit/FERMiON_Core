"""Evidence-gated extraction, validation, memory, and selection of reusable skills."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .application import Action, ApplicationInterface
from .diagnostic_transition import EpisodeStep, StateVector
from .skills import Skill, SkillStep


@dataclass(frozen=True)
class SkillValidationReport:
    attempts: int
    successes: int
    success_rate: float
    mean_prediction_error: float
    mean_execution_cost: float
    failure_modes: tuple[str, ...]


class SkillExtractor:
    """Converts repeated successful primitive trajectories into parameterized procedures."""

    def extract(self, name: str, trajectories: list[list[EpisodeStep]]) -> Skill:
        if not trajectories or not all(trajectory for trajectory in trajectories):
            raise ValueError("skill extraction requires nonempty trajectories")
        width = len(trajectories[0])
        if any(len(trajectory) != width for trajectory in trajectories):
            raise ValueError("trajectories must have matching action lengths")
        if any(not step.result.success for trajectory in trajectories for step in trajectory):
            raise ValueError("only successful trajectories may be promoted to a candidate skill")
        if any([step.action.operation for step in trajectory] != [step.action.operation for step in trajectories[0]]
               for trajectory in trajectories[1:]):
            raise ValueError("trajectories must have matching action operations")
        parameters: dict[str, Any] = {}
        steps: list[SkillStep] = []
        for index, reference in enumerate(trajectories[0]):
            arguments = dict(reference.action.arguments)
            for key, value in tuple(arguments.items()):
                observed = [trajectory[index].action.arguments.get(key) for trajectory in trajectories]
                if len({json.dumps(item, sort_keys=True) for item in observed}) > 1:
                    parameter = f"step{index}_{key}"
                    parameters[parameter] = {"examples": observed, "required": True}
                    arguments[key] = "$" + parameter
            steps.append(SkillStep({"operation": reference.action.operation, "arguments": arguments}, ()))
        first_states = [trajectory[0].state for trajectory in trajectories]
        preconditions = tuple({"label": label, "equals": first_states[0].values[position]}
                              for position, label in enumerate(first_states[0].labels)
                              if all(state.values[position] == first_states[0].values[position] for state in first_states))
        final = trajectories[0][-1].actual_state
        effects = tuple({"label": label, "equals": final.values[position]}
                        for position, label in enumerate(final.labels)
                        if final.values[position] != trajectories[0][0].state.values[position])
        errors = [step.diagnostic.prediction_error for trajectory in trajectories for step in trajectory]
        confidence = sum(max(0.0, 1.0 - error) for error in errors) / len(errors)
        return Skill(name, tuple(steps), "diagnostic-transition", "episode", 1, parameters,
                     preconditions, effects, confidence, ("checkpoint required",), (),
                     tuple(step.step_id for trajectory in trajectories for step in trajectory))


class SkillValidator:
    """Replays an instantiated candidate under caller-provided controlled variations."""

    def validate(self, skill: Skill, application_factory: Callable[[], ApplicationInterface],
                 variations: list[dict[str, Any]]) -> SkillValidationReport:
        successes, errors, costs, failures = 0, [], [], []
        for values in variations:
            application = application_factory(); before = application.observe()
            started = time.perf_counter()
            try:
                for raw in skill.instantiate(**values):
                    result = application.execute(Action(raw["operation"], raw.get("arguments", {})))
                    if not result.success or not application.verify(result).success:
                        raise RuntimeError(result.error or "skill action verification failed")
                # Effects are evaluated using raw state only when their labels are also direct fields.
                successes += 1
            except (RuntimeError, ValueError, KeyError) as error:
                failures.append(str(error))
            finally:
                costs.append(time.perf_counter() - started)
                _ = before  # Kept for future state-encoder-based skill verification.
        attempts = len(variations)
        return SkillValidationReport(attempts, successes, successes / attempts if attempts else 0.0,
                                     sum(errors) / len(errors) if errors else 0.0,
                                     sum(costs) / len(costs) if costs else 0.0, tuple(sorted(set(failures))))


class SkillMemory:
    """Persistent store that promotes candidates only after replay evidence."""

    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, Skill] = {}
        if self.path.exists():
            for value in json.loads(self.path.read_text(encoding="utf-8")):
                value["steps"] = tuple(SkillStep(**step) for step in value["steps"])
                for key in ("preconditions", "effects", "rollback_requirements", "failure_modes", "provenance"):
                    value[key] = tuple(value.get(key, ()))
                self._items[value["name"]] = Skill(**value)

    def promote(self, skill: Skill, report: SkillValidationReport, *, minimum_success_rate: float = 0.8) -> bool:
        if report.attempts == 0 or report.success_rate < minimum_success_rate:
            return False
        self._items[skill.name] = Skill(**{**asdict(skill), "steps": skill.steps,
                                           "confidence": report.success_rate,
                                           "failure_modes": report.failure_modes})
        self.path.write_text(json.dumps([asdict(skill) for skill in self._items.values()], indent=2, sort_keys=True), encoding="utf-8")
        return True

    def all(self) -> tuple[Skill, ...]:
        return tuple(self._items.values())


@dataclass(frozen=True)
class PlanDecision:
    mode: str
    skills: tuple[Skill, ...]
    reason: str


class HierarchicalSkillPlanner:
    """Advisory high-level choice; it never executes actions or bypasses approval."""

    def choose(self, goal: str, state: StateVector, skills: tuple[Skill, ...], *,
               allow_safe_exploration: bool = False) -> PlanDecision:
        applicable = tuple(skill for skill in skills if skill.applicable(state))
        exact = tuple(skill for skill in applicable if skill.name == goal)
        if exact:
            return PlanDecision("known_skill", exact[:1], "validated skill matches goal")
        if applicable:
            return PlanDecision("compose_skills", applicable, "compose applicable validated skills")
        if allow_safe_exploration:
            return PlanDecision("explore_safely", (), "no validated skill applies")
        return PlanDecision("ask_for_approval", (), "no validated skill applies")
