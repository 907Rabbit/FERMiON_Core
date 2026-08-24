"""Demonstration recorder for observation-action-observation transitions."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .observation import ObservationSnapshot


@dataclass(frozen=True)
class DemonstrationEvent:
    before: ObservationSnapshot
    action: dict[str, Any]
    after: ObservationSnapshot
    timestamp: float


class ActionRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, before: ObservationSnapshot, action: dict[str, Any],
               after: ObservationSnapshot) -> DemonstrationEvent:
        event = DemonstrationEvent(before, action, after, time.time())
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(event), sort_keys=True) + "\n")
        return event

    def read(self) -> list[DemonstrationEvent]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            events.append(DemonstrationEvent(ObservationSnapshot(**raw["before"]), raw["action"],
                                             ObservationSnapshot(**raw["after"]), raw["timestamp"]))
        return events

