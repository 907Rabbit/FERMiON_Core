# CP10-P0.4 consolidated freeze-candidate

Status: `PROVISIONAL_NOT_FROZEN` · implementation authorized: `false` · execution authorized: `false` · scientific verdict: `UNEARNED`.

This standalone draft defines a nondimensional classical mixed Model-B(\(\psi\))/Model-A(\(\Phi\)) surrogate only. It makes no fundamental MFE, matter, geometry, covariance, Liouville, CFT, BCJ, consciousness, quantum, real-world, or CP11 claim.

## Model

On periodic \([0,2\pi)^2\), \(T=10\), with \(\kappa_\psi=m_\psi^2=M_\psi=\kappa_\Phi=M_\Phi=1\), \(\bar\psi=0\):

\[
F=\int[\tfrac12|\nabla\psi|^2+\tfrac12\psi^2+\tfrac12|\nabla\Phi|^2+
\tfrac\lambda4(\Phi^2-v^2)^2-\eta\Phi^2\psi]dx.
\]

\(\mu_\psi=-\Delta\psi+\psi-\eta\Phi^2\), \(\partial_t\psi=\Delta\mu_\psi\); \(\mu_\Phi=-\Delta\Phi+\lambda\Phi(\Phi^2-v^2)-2\eta\Phi\psi\), \(\partial_t\Phi=-\mu_\Phi\). Therefore \(dF/dt=-\int|\nabla\mu_\psi|^2-\int\mu_\Phi^2\le0\) for variational arms.

For \(P'=\Phi^2-\operatorname{mean}(\Phi^2)\), formal mean-zero \(\psi\) elimination gives
\[-\eta^2\langle P',L_\psi^{-1}P'\rangle/2\ge-\eta^2\|P'\|_2^2/4\ge-\eta^2\|\Phi^2\|_2^2/4.\]
Thus \(\lambda>\eta^2\) is sufficient, not necessary; every listed tuple satisfies it.

## Numerics and initial data

Use N=32,64,128; dt=.0025,.00125,.000625; production N64/dt=.00125 only after N128/dt=.000625 calibration. Record every .05 using fixed trapezoid-time and \(dx^2\)-space weights. FFT uses NumPy even ordering, forward \(N^{-2}\), unscaled inverse, Parseval \(dx^2\sum|f|^2=(2\pi)^2\sum|\hat f|^2\), and no original-grid Nyquist state.

Every quadratic/cubic product is evaluated through one 2N padded path: embed retained spectra, inverse, multiply, forward with \((2N)^{-2}\), and restrict. The exact retained band and diagnostics are in JSON. Phi², Phi³, Phi·psi, and Phi(Phi²-v²) must each match direct convolution to \(10^{-12}\).

Initial fields use specified Philox4x32-10 tags/streams, physical signed-mode counters, Box–Muller conversion, Hermitian representatives \(k_y>0\) or \(k_y=0,k_x>0\), zero mean, and RMS .05. Modal tables and arrays are hashed. The simultaneous first-order IMEX updates both fields only from state \(n\); it is not claimed energy stable.

## Arms, hypotheses, and verdict

Arms are eta-zero, full, nonvariational one-way, phase-randomized full, and sign-reversal sensitivity. One-way psi is the eta-zero stored artifact—not a duplicate integration—and H4 requires the same reference, hash, and parent ID. H1 tests Eψ/EΦ; H2 tests Phi feedback; H3 tests positive alignment difference against phase control; H4 is identity only. Every delta uses \(\epsilon_{production}=\epsilon_{space}+\epsilon_{time}\), separately per endpoint.

All 208 unique configurations plus 12 replay attempts are enumerated in the sibling condition manifest. Per-condition and final artifact contracts, bootstrap construction, all startup/hard-stop/convergence/energy rules, and PASS/FAIL/INCONCLUSIVE logic are fully specified in the JSON file. `execution_complete` requires all conditions and finalization to terminate; `gate_pass` additionally requires every applicable validity gate and H1–H4. Missing evidence never passes.
