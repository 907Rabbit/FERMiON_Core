# Self-evolver boundary

The only supported FERMiON self-evolver engine is
`fermion.safe_self_evolver` (`fermion.safe_self_evolver.v1`). The dashboard
adapter, `python -m fermion self-evolver`, and the root
`safe_self_evolver.py` convenience entry point all resolve to this engine.

`fermion.software.safe_self_evolver` remains in the tree as a legacy,
forensic-compatible module. It is not an adapter target, CLI target, or
promotion source. Do not point an existing evolver workspace at both engines:
their state and audit contracts are separate.

The canonical engine may modify only generated strategy files inside its
configured workspace. The controller, evaluator, promotion threshold, and
adapter boundary remain outside its mutation scope. A promoted strategy is not
a claim of scientific, agentic, or system-level improvement.
