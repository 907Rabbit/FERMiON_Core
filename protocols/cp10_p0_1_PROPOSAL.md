# CP10-P0.1 — provisional matter-coupling gate contract

Status: `PROVISIONAL_NOT_FROZEN`  
Implementation authorized: `false`  
Execution authorized: `false`  
Scientific verdict: `UNEARNED`

This is a draft contract only. It does not implement CP10, run a solver, access final-test data, modify the scientific-gate registry, or issue a scientific verdict.

## Question and scope

Does adding a real field \(\Phi\), with symmetry breaking and controlled coupling to a frozen \(\psi\) sector, yield finite, stable, convergent, reproducible dynamics measurably distinct from matched uncoupled and negative-control systems?

The candidate action is:

\[
S_{\mathrm{CP10}}=S_\psi+\int\left[\tfrac12|\nabla\Phi|^2+
\tfrac{\lambda_\Phi}{4}(\Phi^2-v_\Phi^2)^2-\eta\Phi^2\psi\right]dx.
\]

This proposal makes no geometry, \(\Omega\), quantum, Liouville, CFT, BCJ, consciousness, or CP11 claim. Geometry is a separately specified prerequisite/factorial arm.

## Proposed equations

P0.1 assumes a frozen, constant-mobility Model-B \(\psi\) baseline and a Model-A \(\Phi\) field. That metric choice is provisional and must be recorded before any run.

\[
\mu_\psi=\frac{\delta S_\psi}{\delta\psi}-\eta\Phi^2,
\qquad
\mu_\Phi=-\Delta\Phi+\lambda_\Phi\Phi(\Phi^2-v_\Phi^2)-2\eta\Phi\psi,
\]

\[
\partial_t\psi=M_\psi\Delta\mu_\psi,
\qquad
\partial_t\Phi=-M_\Phi\mu_\Phi.
\]

These derivatives follow from the candidate action; the dynamics additionally follow from the declared \(H^{-1}\) and \(L^2\) metrics. CP10 cannot start until the exact \(S_\psi\), baseline source/config hash, initial-condition generator, boundary condition, and baseline validation receipt are frozen.

## Proposed numerical protocol

- Domain: \([0,2\pi)^2\); periodic in both dimensions.
- Grids: \(N=32,64,128\); final time \(T=10\).
- Integrator: Fourier pseudo-spectral block semi-implicit IMEX, constant coefficients implicit and nonlinear terms explicit; apply 2/3 de-aliasing.
- Time-step hierarchy: \(0.0025,0.00125,0.000625\).
- \(\psi\)'s zero Fourier mode must be preserved exactly. \(\Phi\) has no claimed mass invariant.
- Do not claim monotone discrete free-energy decrease unless it is separately derived for the selected IMEX scheme.

Use matched frozen-baseline \(\psi\) initial states. Initialize \(\Phi\) as a zero-mean band-limited Gaussian field (standard deviation 0.05, \(|k|\le4\)). Calibration seeds are 1–8; held-out evaluation seeds are 1001–1016. No learned component is included; a learned replacement would require a separate train/calibration/test split and protocol revision.

Parameters are fixed before execution: \(M_\psi=M_\Phi=1\), \(\lambda_\Phi\in\{0.5,1,2\}\), \(v_\Phi\in\{0.5,1\}\), and \(\eta\in\{0,0.05,0.1\}\). The primary target is \((\lambda_\Phi,v_\Phi,\eta)=(1,1,0.1)\). Calibration can only validate software; it cannot select parameters, endpoints, or thresholds.

## Controls, observables, and gate

The uncoupled baseline is \(\eta=0\). Negative controls are frozen-\(\psi\) feedback ablation, deterministic Fourier-phase-permuted \(\psi\) preserving amplitudes and zero mode, and a sign-reversed \(+\eta\Phi^2\psi\) structural arm.

The primary endpoint for matched seed \(s\) is

\[
E_s=\frac{\sqrt{\operatorname{mean}_{t\in[1,10],x}(\psi_\eta-\psi_0)^2}}
{\max(\sqrt{\operatorname{mean}_{t\in[1,10],x}\psi_0^2},10^{-12})}.
\]

Report the mean and a two-sided percentile 95% bootstrap confidence interval over 16 held-out seeds (10,000 deterministic resamples; bootstrap seed 20260825). The effect criterion requires its lower confidence endpoint to exceed \(\max(0.02,3\max(\text{spatial error},\text{temporal error}))\), with controls not both meeting that criterion.

Hard validity checks are: zero non-finite values; exact \(\psi\) zero-mode error at most \(10^{-12}\) in float64; finite energy/fields with \(|\Phi|,|\psi|\le10^6\); the predeclared energy-law residual limits; spatial errors of at most 0.15 (32→64) and 0.05 (64→128); temporal error at most 0.02 between \(dt/2\) and \(dt/4\); spectral-tail fraction at most \(10^{-4}\); and exact deterministic reruns for seeds 1001, 1008, and 1016. Full definitions, justification, and failure interpretation are in the JSON contract.

Every condition requires configuration, source/environment, RNG, input/output hashes, diagnostics, snapshots, spectra, convergence reports, stdout/stderr, and an immutable finalizer record. Any missing provenance, hard-stop, unresolved convergence, or post-start change creates `FAIL_OR_INCONCLUSIVE`; no threshold may be changed in place.

## Earned and unearned claims

If every gate passes, the only earned claim is a bounded numerical one: within this frozen P0.1 periodic mixed-flow protocol and tested parameter grid, the declared coupling yielded finite, stable, convergent, deterministic, control-separated dynamics measurably distinct from \(\eta=0\).

Geometry, general covariance, \(\Omega\), quantum, Liouville, CFT, BCJ, consciousness, universal physical validity, and CP11 all remain unearned. CP11 remains gated because no authoritative definition was recovered; it additionally requires CP10 receipts and a separately frozen question, action, controls, and—if geometry is proposed—its own geometry factorial arm and gauge/boundary audits.
