"""Small, explicit scientific-analysis utilities used by the cognitive runtime."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class VariationalSystem:
    functional: str
    metric_operator: str

def cahn_hilliard_mass_analysis() -> dict[str, str]:
    return {"functional": "F[c] = ∫(f(c) + κ|∇c|²/2) dx", "metric_operator": "K = -∇·M∇ (H⁻¹ gradient-flow metric)", "invariant": "d/dt ∫c dx = ∫∇·(M∇μ) dx = ∮M∇μ·n dS = 0 for periodic or no-flux boundaries"}

def model_a_b_reference() -> dict[str, str]:
    """Authoritative Allen-Cahn/Cahn-Hilliard comparison for the built-in linter."""
    return {"model_a": "Allen-Cahn: K = I (or positive mobility M), L2 metric; dF/dt = -integral(mu^2) dx <= 0; mass is not generically conserved; equilibrium mu = 0; second-order PDE.", "model_b": "Cahn-Hilliard: K = -Delta, H^-1 metric; dF/dt = -integral(|grad(mu)|^2) dx <= 0; mass is conserved for periodic/no-flux boundaries; equilibrium mu = constant; fourth-order PDE and explicit stability is typically dt = O(dx^4).", "double_well": "For W(psi) = (psi^2 - 1)^2/4, minima are psi = -1 and psi = 1; psi = 0 is the barrier maximum."}

def lint_variational_claims() -> list[dict[str, str]]:
    return [{"code": "PHI3501", "level": "ERROR", "message": "The same F does not define the same dynamics: K_A = I and K_B = -Delta are different operators."}, {"code": "PHI3201", "level": "ERROR", "message": "Energy dissipation does not imply mass conservation; Allen-Cahn does not generically conserve mass."}, {"code": "PHI3401", "level": "WARNING", "message": "A continuous Lyapunov identity does not guarantee monotone discrete timesteps."}, {"code": "PHI3504", "level": "ERROR", "message": "The R² law is an Allen-Cahn/mean-curvature benchmark, not generic Cahn-Hilliard behavior."}]
