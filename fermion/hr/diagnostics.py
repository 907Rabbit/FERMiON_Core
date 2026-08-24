"""Machine-readable decision traces and human-readable explanations."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .contracts import DecisionTrace


class DiagnosticRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, trace: DecisionTrace) -> None:
        payload = {"timestamp": time.time(), **asdict(trace)}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True) + "\n")

    def read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


def explain_decision(trace: DecisionTrace) -> str:
    ordered = sorted(trace.scores, key=lambda score: score.total)
    selected = next(score for score in ordered if score.candidate_id == trace.selected_id)
    strongest = sorted(trace.energy_terms.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
    drivers = ", ".join(f"{name}={value:.4f}" for name, value in strongest)
    runner_up = ordered[1].candidate_id if len(ordered) > 1 else "none"
    return (f"Selected {selected.candidate_id} with score {selected.total:.4f}; "
            f"runner-up: {runner_up}. Dominant energy terms: {drivers}.")

