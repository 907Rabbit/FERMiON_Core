"""Domain-neutral scientific model, constraints, and deterministic solver planning."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping


@dataclass(frozen=True)
class ScientificVariable:
    id: str
    unit: str
    nonnegative: bool = False

@dataclass(frozen=True)
class ScientificModelIR:
    domain: str
    problem_class: str
    variables: tuple[ScientificVariable, ...]
    parameters: Mapping[str, float]
    parameter_units: Mapping[str, str]
    conserved_quantities: tuple[str, ...]

@dataclass(frozen=True)
class Constraint:
    id: str
    kind: str  # equality, inequality, constitutive_relation
    semantic: str

@dataclass(frozen=True)
class ConstraintIR:
    constraints: tuple[Constraint, ...]
    residual_tolerances: Mapping[str, float]

@dataclass(frozen=True)
class SolverPlan:
    problem_definition: str
    solver_name: str
    variable: str
    bracket: tuple[float, float]
    residual_tolerance: float

@dataclass(frozen=True)
class LoweredScalarProblem:
    model: ScientificModelIR
    constraints: ConstraintIR
    plan: SolverPlan
    residual: Callable[[float], float]
    species_from_root: Callable[[float], Mapping[str, float]]


def lower_diprotic_acid(*, concentration: float, ka1: float, ka2: float, kw: float, sodium: float) -> LoweredScalarProblem:
    """Chemistry translator: meaning first, then a scalar charge-balance solve plan."""
    if min(concentration, ka1, ka2, kw, sodium) < 0 or any(value == 0 for value in (concentration, ka1, ka2, kw)):
        raise ValueError("diprotic parameters must be positive; sodium must be nonnegative")
    model = ScientificModelIR("chemistry", "diprotic_acid_speciation",
        (ScientificVariable("H", "mol/L", True), ScientificVariable("H2A", "mol/L", True),
         ScientificVariable("HA", "mol/L", True), ScientificVariable("A2", "mol/L", True),
         ScientificVariable("OH", "mol/L", True), ScientificVariable("Na", "mol/L", True)),
        {"C": concentration, "Ka1": ka1, "Ka2": ka2, "Kw": kw, "Na": sodium},
        {"C": "mol/L", "Ka1": "mol/L", "Ka2": "mol/L", "Kw": "(mol/L)^2", "Na": "mol/L"}, ("total_acid", "charge"))
    constraints = ConstraintIR((
        Constraint("diprotic_distribution_relations", "constitutive_relation", "D=H^2+Ka1*H+Ka1*Ka2; species distributions"),
        Constraint("mass_balance", "equality", "C=H2A+HA+A2"),
        Constraint("charge_balance", "equality", "H+Na=HA+2*A2+OH"),
        Constraint("Ka1", "equality", "Ka1=H*HA/H2A"), Constraint("Ka2", "equality", "Ka2=H*A2/HA"),
        Constraint("Kw", "equality", "Kw=H*OH"), Constraint("nonnegative", "inequality", "all concentrations >= 0")),
        {"mass_balance": 1e-10, "charge_balance": 1e-10, "relative_ka1": 1e-10, "relative_ka2": 1e-10, "relative_kw": 1e-10})
    plan = SolverPlan("bounded nonlinear algebraic charge-balance root", "bracketed_scalar_root", "log10_H", (-14.0, 0.0), 1e-14)
    def species(log_h: float) -> Mapping[str, float]:
        h = 10.0 ** log_h; d = h*h + ka1*h + ka1*ka2
        return {"H": h, "H2A": concentration*h*h/d, "HA": concentration*ka1*h/d,
                "A2": concentration*ka1*ka2/d, "OH": kw/h, "Na": sodium}
    def residual(log_h: float) -> float:
        values = species(log_h)
        return values["H"] + sodium - values["HA"] - 2*values["A2"] - values["OH"]
    return LoweredScalarProblem(model, constraints, plan, residual, species)


def normalized_semantics(lowered: LoweredScalarProblem) -> dict[str, object]:
    """Comparable golden contract; intentionally excludes run-specific receipt fields."""
    return {"classification": (lowered.model.domain, lowered.model.problem_class),
            "parameters_and_units": {key: (lowered.model.parameters[key], lowered.model.parameter_units[key]) for key in sorted(lowered.model.parameters)},
            "constraint_semantics": tuple((item.id, item.kind, item.semantic) for item in lowered.constraints.constraints),
            "solver_problem_definition": (lowered.plan.problem_definition, lowered.plan.variable, lowered.plan.bracket, lowered.plan.residual_tolerance),
            "tolerances": dict(lowered.constraints.residual_tolerances)}
