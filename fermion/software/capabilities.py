"""Persistent registry of verified, versioned software capabilities."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Capability:
    name: str
    application: str
    interface: str
    verified_successes: int = 0
    verified_failures: int = 0
    reversible: bool = True
    metadata: dict[str, Any] | None = None

    @property
    def reliability(self) -> float:
        return (self.verified_successes + 1) / (self.verified_successes + self.verified_failures + 2)


class CapabilityRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, Capability] = {}
        if self.path.exists():
            self._items = {item["name"]: Capability(**item)
                           for item in json.loads(self.path.read_text(encoding="utf-8"))}

    def _save(self) -> None:
        self.path.write_text(json.dumps([asdict(item) for item in self._items.values()], indent=2,
                                        sort_keys=True), encoding="utf-8")

    def put(self, capability: Capability) -> None:
        self._items[capability.name] = capability
        self._save()

    def record_outcome(self, name: str, success: bool) -> Capability:
        current = self._items[name]
        updated = Capability(current.name, current.application, current.interface,
                             current.verified_successes + int(success),
                             current.verified_failures + int(not success),
                             current.reversible, current.metadata)
        self.put(updated)
        return updated

    def get(self, name: str) -> Capability | None:
        return self._items.get(name)

    def all(self) -> tuple[Capability, ...]:
        return tuple(self._items.values())

