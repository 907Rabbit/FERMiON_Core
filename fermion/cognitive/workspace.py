"""Global workspace selection and functional cognitive-access metrics."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import torch

@dataclass(frozen=True)
class WorkspaceBroadcast:
    selected: tuple[str, ...]; occupancy: float; integration: float

class GlobalWorkspace:
    def broadcast(self, candidates: dict[str, float], limit: int = 6) -> WorkspaceBroadcast:
        ranked = sorted(candidates.items(), key=lambda pair: pair[1], reverse=True)[:limit]
        scores = [max(0., value) for _, value in ranked]
        occupancy = min(1., len(ranked) / limit)
        integration = float(sum(scores) / len(scores)) if scores else 0.
        return WorkspaceBroadcast(tuple(name for name,_ in ranked), occupancy, min(1., integration))

def access_metrics(state: Any, workspace: WorkspaceBroadcast) -> dict[str, object]:
    confidence = float(state.confidence_state.item()); novelty = float(state.novelty_state.item())
    recurrence = min(1., float(state.time_state.item()) / 3.)
    differentiation = min(1., float(torch.std(state.psi).item()) + .4)
    availability = min(1., workspace.occupancy * .6 + workspace.integration * .4)
    return {"workspace_activation": workspace.occupancy, "global_availability": availability, "integration": workspace.integration, "differentiation": differentiation, "recurrence": recurrence, "self_model_activity": min(1., float(torch.linalg.vector_norm(state.self_state).item()) / 4.), "temporal_continuity": recurrence, "metacognitive_confidence": confidence, "novelty": novelty, "prediction_error": novelty, "conscious_access_proxy": sum((availability, workspace.integration, recurrence, confidence)) / 4., "phenomenal_status": "indeterminate"}
