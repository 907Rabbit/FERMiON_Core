"""Controlled FERMiON-HR ablation configurations."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .config import HRConfig


@dataclass(frozen=True)
class Ablation:
    name: str
    refinement_steps: int = 3
    use_psi: bool = True
    use_memory: bool = True
    decompose_energy: bool = True
    use_uncertainty: bool = True


ABLATIONS = (
    Ablation("full"),
    Ablation("no_recursion", refinement_steps=0),
    Ablation("one_refinement", refinement_steps=1),
    Ablation("no_psi", use_psi=False),
    Ablation("no_episodic_memory", use_memory=False),
    Ablation("shuffled_memory"),
    Ablation("no_energy_decomposition", decompose_energy=False),
    Ablation("no_uncertainty", use_uncertainty=False),
)


def config_for(base: HRConfig, ablation: Ablation) -> HRConfig:
    return replace(base, refinement_steps=ablation.refinement_steps)

