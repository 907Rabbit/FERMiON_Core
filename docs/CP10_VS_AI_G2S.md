# CP10 vs AI-G2S status audit

Both tracks are **gated_preexecution**. Neither has an earned scientific verdict. They are independent: CP10 must not import AI-G2S runners; AI-G2S must not mutate the 193-parameter specimen.

## Side-by-side

| | CP10 | AI-G2S |
|---|---|---|
| Gate id | `CP10` | `AI-G2S-P1.0` blocked; `AI-G2S-P1.1` gated_preexecution |
| Authoritative protocol | CP10-P0.10 freeze receipt (2026-08-26) | `configs/ai_g2s_p1_1.json` (parent P1.0 hash pinned) |
| What is frozen | Oracle-A **implementation protocol**, fixtures, run tuples, thresholds | Paired spectral-utility evaluation contract, RNG seeds, dataset cardinalities |
| Source package | `fermion/cp10/` | `fermion/ai_g1/ai_g2s*.py` |
| CLI | `python -m fermion cp10 verify` (PASS, 12 members). `smoke` opt-in. `full` gated. | `python -m fermion ai-g2s-verify`. No full-matrix command. |
| Control-plane op | `fermion_science.verify_cp10_bundle` | `fermion_science.verify_ai_g2s_manifest` |
| Allowed now | Bundle hash verify; optional calibration-only smoke (non-scientific) | Source/config hash verify; calibration smoke artifacts exist (`test_data_accessed: false`) |
| Unauthorized | Oracle-A trajectory, Oracle B, held-out seeds 1001–1016, bootstrap inference, scientific-condition run, CP10 verdict, CP11 | Full paired matrix (5 tasks × 6 models × 3 seeds = 90 training conditions), final test predictions, promotion via `spectral_utility_gate` |
| Scientific status | Verdict **UNEARNED** | `SPECTRAL_UTILITY_UNEARNED` |
| Parent leftover | P0.9 unfrozen, prospectively superseded. P0.8 still used by `cp10.runner` / `frozen_protocol` for R1 source tests. | P1.0 coverage artifact still **BLOCKED** on missing scientific values; P1.1 was the correction. |

## CP10 evidence actually on disk

P0.10 freeze assertions (`protocols/cp10_p0_10_FREEZE_RECEIPT.json`):

- `oracle_trajectory_executed`: false
- `solver_executed`: false
- `held_out_seed_accessed`: false
- Oracle-A source implementation: AUTHORIZED
- Oracle-A trajectory: UNAUTHORIZED

P0.9 left a one-shot **static** manufactured-PDE residual matrix (278 checks, residuals ~1e-16). That is not a trajectory and does not un-gate P0.10 execution.

`fermion/cp10/oracle_a_p0_10.py` can construct frozen RunSpecs and verify the bundle. It must not timestep without a future launch record.

`fermion/cp10/runner.py` `full` still `SystemExit`s: a detached authorized launch record is required.

## AI-G2S evidence actually on disk

- P1.0 `artifacts/ai_g2s_r1/protocol_coverage.json`: runner **BLOCKED**; several scientific values unspecified.
- P1.1 repaired launch-readiness: `REPAIRED_PREEXECUTION_EVIDENCE_PASS`; `full_paired_execution: GATED_PENDING_EXPLICIT_LAUNCH_AUTHORIZATION`; `final_test_predictions: NONE`.
- Calibration-only smoke: 30 conditions, test data not accessed, `scientific_verdict: null`.
- `spectral_utility_gate` requires paired relative-error wins; it has not been applied to a completed full matrix.

Partial checkpoints under `artifacts/ai_g2s_p1_1_full/` are **not** a scientific result.

## Do not conflate

1. Hash-verified source ≠ experiment run.
2. Calibration smoke ≠ held-out or final test.
3. CP10 P0.8 R1 source tests ≠ P0.10 Oracle-A trajectories.
4. Wiring `verify_*` into chat/control plane does not authorize solvers.
