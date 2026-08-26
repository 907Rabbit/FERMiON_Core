# CP10-P0.2 — review-only revision

Status: `PROVISIONAL_NOT_FROZEN`  
Implementation authorized: `false`  
Execution authorized: `false`  
Scientific verdict: `UNEARNED`

This revises CP10-P0.1 without changing it. CP10-P0.2 is a nondimensional classical mixed-gradient-flow surrogate, not a fundamental MFE, matter, geometry, or quantum action.

## Model and continuous check

\[
F_\psi=\tfrac12\int[\kappa_\psi|\nabla\psi|^2+m_\psi^2(\psi-\bar\psi)^2]dx,
\]

with \(\kappa_\psi=m_\psi^2=M_\psi=1\), \(\bar\psi=0\), and provisional \(\kappa_\Phi=M_\Phi=1\). The complete proposal is

\[
F=\int[\tfrac{\kappa_\psi}{2}|\nabla\psi|^2+\tfrac{m_\psi^2}{2}(\psi-\bar\psi)^2+
\tfrac{\kappa_\Phi}{2}|\nabla\Phi|^2+\tfrac{\lambda_\Phi}{4}(\Phi^2-v_\Phi^2)^2-\eta\Phi^2\psi]dx.
\]

Periodic integration by parts gives

\[
\mu_\psi=-\kappa_\psi\Delta\psi+m_\psi^2(\psi-\bar\psi)-\eta\Phi^2,
\quad\partial_t\psi=M_\psi\Delta\mu_\psi,
\]
\[
\mu_\Phi=-\kappa_\Phi\Delta\Phi+\lambda_\Phi\Phi(\Phi^2-v_\Phi^2)-2\eta\Phi\psi,
\quad\partial_t\Phi=-M_\Phi\mu_\Phi.
\]

Thus \(dF/dt=-M_\psi\int|\nabla\mu_\psi|^2dx-M_\Phi\int\mu_\Phi^2dx\le0\). This is independently checked by a pre-run finite-difference directional derivative audit. It is a continuous identity only, not a claim of discrete monotonicity.

## Fixed spectral conventions

Use float64/complex128 on \([0,2\pi)^2\), \(dx=2\pi/N\), with
\(\hat f_{pq}=N^{-2}\sum_{jl}f_{jl}e^{-i(k_xx_j+k_yy_l)}\) and the unscaled inverse. For even \(N\), use frequency ordering \([0,1,\ldots,N/2,-N/2+1,\ldots,-1]\), Laplacian symbol \(-(k_x^2+k_y^2)\), and Parseval \(dx^2\sum|f|^2=(2\pi)^2\sum|\hat f|^2\). Real fields obey Hermitian symmetry; the four modes with each index 0 or \(N/2\) are self-conjugate and real.

Startup hard audits are FFT round trip < \(10^{-14}\), Parseval < \(10^{-13}\), analytic spectral derivative < \(10^{-12}\), zero-mode preservation, directional derivative < \(10^{-6}\), and a manufactured or independent convergence oracle.

Nonlinear products use the rectangular 2/3 mask \(|k_x|\le N/3\) **and** \(|k_y|\le N/3\). Record both pre-filter nonlinear energy removed (limit 0.10) and resolved-state energy in \(0.8N/3\le\max(|k_x|,|k_y|)\le N/3\) (limit 0.02). These are distinct resolution diagnostics; a post-filter empty band is not one.

## Pairing, controls, and endpoints

Use Philox4x32-10 indexed by seed, field tag, Fourier mode, and component. Generate \(\psi_0\) and \(\Phi_0\) exactly once per seed; impose Hermitian symmetry, hash canonical float64 arrays, and reuse the same continuum Fourier realization at every arm, grid, and time step. Fine grids zero-pad rather than redraw.

The target is \(\eta=.1,\lambda_\Phi=1,v_\Phi=1\); baseline is \(\eta=0\) with identical fields. Null controls are one-way \(\Phi\) response, Hermitian phase-permuted \(\psi\), and a predeclared cyclic label permutation. Sign reversal is mechanistic sensitivity only.

Record every .05 time units through \(T=10\), and use fixed trapezoid time weights and \(dx^2\) spatial weights for trajectory norms. Report \(E_\psi\), \(E_\Phi\), and both full-versus-one-way feedback endpoints. The one-way control's \(\psi\) difference is zero by construction, so it is not evaluated using that endpoint alone.

The full target must exceed **each** null control by \(\delta=\max(.01,3\max(\text{spatial},\text{temporal error}))\), with paired 95% bootstrap intervals excluding zero. Intended no-feedback equivalence requires its entire CI inside \([-\delta,\delta]\); non-rejection alone is not equivalence.

## Validity, convergence, and staged scope

All fields, final states, trajectory norms, energy trajectories, and endpoints converge only after fine fields are restricted to their common Fourier band. Floors are \(10^{-12}\); 32→64 and 64→128 errors must be at most .15 and .05, and the finest two time steps at most .02. Accumulate dissipation at every accepted step and require refined \(R_E\), without claiming exact discrete monotonicity.

The 16 held-out seeds are random initial-condition realizations, not experimental subjects. Use 10,000 paired Philox bootstrap resamples, `np.quantile(..., method="linear")`, ratio recomputation inside each replicate, and a hashed index manifest. Their count cannot change after outcomes are observed.

Stages are fixed before freezing: A audits (0 simulations); B 80 calibration conditions; C 144 refinement conditions; D 32 sensitivity conditions; E 95 held-out/replay conditions—351 total. The JSON contract contains the exact arms and counts.

The sole possible eventual claim is a bounded numerical claim for this classical system. CP11, geometry, covariance, Liouville, CFT, BCJ, consciousness, quantum advantage, and real-world matter claims remain gated.
