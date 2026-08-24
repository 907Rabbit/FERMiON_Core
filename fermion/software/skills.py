"""Compilation of demonstrations into reusable, validator-bound skills."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .recorder import DemonstrationEvent


@dataclass(frozen=True)
class SkillStep:
    action: dict[str, Any]
    expected_changes: tuple[str, ...]


@dataclass(frozen=True)
class Skill:
    name: str
    steps: tuple[SkillStep, ...]
    validator_name: str
    source: str = "demonstration"
    version: int = 1
    parameters: dict[str, Any] = field(default_factory=dict)
    preconditions: tuple[dict[str, Any], ...] = ()
    effects: tuple[dict[str, Any], ...] = ()
    confidence: float = 0.0
    rollback_requirements: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    backend_provenance: dict[str, Any] = field(default_factory=dict)

    def applicable(self, state: Any) -> bool:
        """Check declarative equality preconditions against a labeled state vector."""
        values = dict(zip(getattr(state, "labels", ()), getattr(state, "values", ())))
        return all(values.get(item.get("label")) == item.get("equals") for item in self.preconditions)

    def instantiate(self, **kwargs: Any) -> tuple[dict[str, Any], ...]:
        missing = set(self.parameters) - set(kwargs)
        if missing:
            raise ValueError(f"missing skill parameters: {sorted(missing)}")
        def replace(value: Any) -> Any:
            if isinstance(value, str) and value.startswith("$"):
                return kwargs[value[1:]]
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            if isinstance(value, list):
                return [replace(item) for item in value]
            return value
        return tuple(replace(step.action) for step in self.steps)

    def verify(self, before: Any, after: Any) -> bool:
        values = dict(zip(getattr(after, "labels", ()), getattr(after, "values", ())))
        return all(values.get(effect.get("label")) == effect.get("equals")
                   for effect in self.effects if "equals" in effect)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DemonstrationSkillCompiler:
    def compile(self, name: str, events: list[DemonstrationEvent], validator_name: str) -> Skill:
        if not events:
            raise ValueError("cannot compile an empty demonstration")
        steps = []
        for event in events:
            before = event.before.channels.get("filesystem", {})
            after = event.after.channels.get("filesystem", {})
            changes = tuple(sorted(path for path in set(before) | set(after)
                                   if before.get(path) != after.get(path)))
            steps.append(SkillStep(event.action, changes))
        return Skill(name, tuple(steps), validator_name)
