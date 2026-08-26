# CP10-P0.6 final freeze-candidate

Status: `PROVISIONAL FINAL FREEZE CANDIDATE`  
Implementation: `UNAUTHORIZED` · Execution: `UNAUTHORIZED` · CP10 verdict: `UNEARNED` · CP11: `GATED`.

This standalone candidate is the nondimensional classical periodic Model-B(psi)/Model-A(Phi) surrogate specified by its JSON companion. It retains the full P0.5 free energy, PDEs, sufficient coercivity bound, float64/complex128 FFT normalization, 2N padded quadratic/cubic products, Philox modal initialization and literal vectors, simultaneous first-order IMEX, startup/manufactured oracles, artifact/resume contracts, energy audit scope, and PASS/FAIL/INCONCLUSIVE semantics. It claims neither physical matter coupling nor any fundamental, geometry, quantum, or CP11 result.

The correction is complete H2 refinement. Stage C spatial and temporal families now include eta-zero, full, and `one_way` for every calibration seed. H2 uses the conservative finite margin

\[
\epsilon_{\rm production,feedback}=(\epsilon_{\rm space,full}+\epsilon_{\rm time,full})+(\epsilon_{\rm space,oneway}+\epsilon_{\rm time,oneway}),\qquad
\delta_{\rm feedback}=\max(0.01,3\epsilon_{\rm production,feedback}).
\]

H2 is INCONCLUSIVE without all four finite refinement terms. H3 remains \(\Delta A_s=A_{full,s}-A_{eta0,s}\), with the analogous sum of full and eta-zero space/time errors. All endpoint estimands are arithmetic means of finite seed-level quantities. Each paired bootstrap resamples the same frozen 10,000×16 index array for all compared arms and recomputes means of those seed-level ratios; no pooled-sum or independently bootstrapped ratio is permitted.

The complete condition manifest contains B=24, C=120, D=32, E=48: 224 unique conditions; plus 9 RNG replay attempts for 233 total execution records. Every condition/replay record and parent link is explicit in the sibling manifest.
