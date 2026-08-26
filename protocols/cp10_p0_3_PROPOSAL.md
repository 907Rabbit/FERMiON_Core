# CP10-P0.3 — review-only cubic-safe revision

Status: `PROVISIONAL_NOT_FROZEN` · implementation authorized: `false` · execution authorized: `false` · scientific verdict: `UNEARNED`.

P0.3 is a nondimensional classical Model-B(\(\psi\))/Model-A(\(\Phi\)) surrogate. It does not claim fundamental matter, MFE, geometry, covariance, quantum, Liouville, CFT, BCJ, consciousness, or real-world validity.

## Continuous model and lower bound

With \(\kappa_\psi=m_\psi^2=M_\psi=\kappa_\Phi=M_\Phi=1\) and \(\bar\psi=0\), use the P0.2 free energy and
\(\mu_\psi=-\Delta\psi+\psi-\eta\Phi^2\), \(\mu_\Phi=-\Delta\Phi+\lambda_\Phi\Phi(\Phi^2-v_\Phi^2)-2\eta\Phi\psi\). The flows are \(\partial_t\psi=\Delta\mu_\psi\), \(\partial_t\Phi=-\mu_\Phi\), hence \(dF/dt=-\int|\nabla\mu_\psi|^2-\int\mu_\Phi^2\le0\) continuously.

For mean-zero \(\psi\), eliminating its nonzero modes gives a negative term no smaller than \(-\eta^2\int\Phi^4/4\), because \(-\Delta+1\) has smallest nonzero eigenvalue two. Thus \(\lambda_\Phi>\eta^2\) is sufficient for quartic coercivity. Every proposed pair passes: the minimum \(\lambda_\Phi-\eta^2\) is .49. This mathematical bound, numerical boundedness, and the arbitrary \(10^6\) overflow guard are distinct.

## Fourier and nonlinear products

Use float64/complex128 on \([0,2\pi)^2\), NumPy even ordering \([0,\ldots,N/2-1,-N/2,\ldots,-1]\), and dynamic band \(\max(|k_x|,|k_y|)\le K_N=N/2-1\). Original-grid Nyquist lines never evolve. Forward FFT is normalized by \(N^{-2}\); inverse is unscaled; Parseval is \(dx^2\sum|f|^2=(2\pi)^2\sum|\hat f|^2\). First derivatives and gradient energy use precisely this dynamic band.

Every quadratic/cubic product—including \(\Phi^2\), \(\Phi^3\), and \(\Phi\psi\)—uses the same frozen 2N padded path: embed retained coefficients unchanged, inverse on 2N, multiply, forward with \((2N)^{-2}\), and restrict to the N dynamic band. There is no state 2/3 mask. Record pre-restriction nonlinear truncation fraction (limit .10) and resolved near-cutoff state energy in \(.8K_N\le\max(|k_x|,|k_y|)\le K_N\) (limit .02), both under refinement.

## Initial conditions, IMEX, and oracles

Each zero-mean field comes once per seed from a Hermitian \(|k|\le4\) continuum modal table using physical signed modes and Philox4x32-10: `key=(low32(seed), high32(seed) XOR field_tag)`, `counter=(zigzag32(kx), zigzag32(ky), component, stream_tag)`, `zigzag32(k)=2k` for \(k\ge0\), otherwise \(-2k-1\). Generic \(z_k=(g_1+ig_2)/\sqrt2\); the zero mode is fixed. Normalize once to RMS .05 and hash the modal table and each physical array at every resolution.

The simultaneous first-order IMEX update uses only state \(n\) padded products on both right-hand sides. It restores Hermitian symmetry only for roundoff (hard fail above \(10^{-13}\)), fixes the \(\psi\) zero mode, and zeros Nyquist lines. It is not claimed energy-stable.

Startup oracles are exact eta-zero spectral \(\psi\) decay and a forced manufactured coupled solution \(\psi=.1e^{-t}\cos x\cos y\), \(\Phi=.1e^{-2t}\sin x\sin y\), with forcing defined in the JSON. Forcing is oracle-only.

## Controls, hypotheses, and scope

At predeclared production \(N=64,dt=.00125\), use eta-zero, full, one-way, and exactly phase-randomized controls; sign reversal is sensitivity only. Production is usable only after calibration establishes its N128/dt=.000625 errors; otherwise terminate INCONCLUSIVE without changing held-out resolution.

H1 tests \(E_\psi,E_\Phi\) against numerical floors, H2 tests full-versus-one-way \(\Phi\) feedback, H3 tests positive spatial correspondence against phase control, and H4 requires one-way \(\psi\) practical equivalence to eta-zero. Algebraically identical \(\psi\) comparisons are reported once, not counted as independent discoveries.

The deduplicated plan contains 220 simulation/replay conditions: B 32, C unique 80, D 32, E 64, replay 12. Canonical tuple IDs are `seed|arm|N|dt|lambda_Phi|v_Phi|eta`; identical hashes are reused and duplicate IDs are a generation failure. See JSON for every tuple rule, statistics, accepted-step energy audit, and all hard stops.
