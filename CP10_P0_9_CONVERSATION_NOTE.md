# CP10-P0.9 conversation note

Date: 2026-08-25 (America/Los_Angeles)

The CP10-P0.9 protocol remains **UNFROZEN**.  P0.9 candidate artifacts and
all earlier frozen protocol artifacts were preserved during this work.

Completed, verified evidence:

- The Stage 2A.2 static manufactured-PDE residual matrix ran exactly once
  from an immutable source snapshot.
- It evaluated 12 analytic residual cases: N = 32, 64, 128 at t = 0, 0.25,
  0.5, and 1.0.
- The result passed: 252 atomic checks, 26 global checks, 278 total checks;
  no failed IDs, warnings, non-finite values, or Nyquist violations.
- Oracle A and Oracle B trajectories were not run.  No timestepping,
  calibration/held-out seed access, scientific condition execution, bootstrap
  inference, CP10 promotion, CP11 action, Git operation, or scientific
  verdict occurred.

Key artifacts:

- `artifacts/cp10_p0_9_verifier_stage_2a2_full_residuals.json`
  SHA-256: `85DBE10EB8379C88270697EF709BE25BE0971B42277A4E6532906964E00736F5`
- `artifacts/cp10_p0_9_verifier_stage_2a2_f2c_execution_receipt.json`
  SHA-256: `E714BF2F0BEF2FFF16A1CB2FA4B547B6C9E83E4D67BB8D386B91A474FD337AA8`
- Immutable execution source:
  `artifacts/cp10_p0_9_verifier_stage_2a2_f2b2_execution_source.py`
  SHA-256: `665BA36B0FC226B6F37778ACDE2DECF51642E2332D60EF41E63EB20C572A34D5`
- Pre-execution manifest:
  `artifacts/cp10_p0_9_verifier_stage_2a2_f2c_preexecution_manifest.json`
  SHA-256: `D6C65C32E8F0B274BFD2AEECF598A6F225DDE3978C16757D3C68827AD8D68F03`

Headline static residual maxima:

- psi: `1.725036376230507e-16` at `N128_t0`
- Phi: `2.892423891301715e-17` at `N064_t0`
- Delta(Phi^2): `1.7250363762305068e-15` at `N128_t0`

Current boundary:

- CP10-P0.9: UNFROZEN
- CP10-R1: BLOCKED pending later authorized oracle-integration work
- CP10 scientific verdict: UNEARNED
- CP11: GATED
