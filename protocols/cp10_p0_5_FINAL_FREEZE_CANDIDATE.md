# CP10-P0.5 final freeze-candidate

Status: `PROVISIONAL_NOT_FROZEN` · implementation authorized: `false` · execution authorized: `false` · scientific verdict: `UNEARNED`.

This is a standalone nondimensional classical mixed-flow surrogate. It does not establish physical matter coupling, fundamental MFE, geometry, quantum advantage, CP11, or any other excluded claim.

The periodic \([0,2\pi)^2\), \(T=10\) free energy is \(F=\int[|\nabla\psi|^2/2+\psi^2/2+|\nabla\Phi|^2/2+\lambda(\Phi^2-v^2)^2/4-\eta\Phi^2\psi]dx\). Its Model-B/Model-A PDEs, continuous law, coercivity inequalities, FFT convention, 2N padded products, Philox construction, literal KAT vectors, IMEX update, audits, thresholds, arms, artifacts, and verdict logic are fully specified in the JSON companion.

The only production arms are eta-zero, full bidirectional, and one-way `NONVARIATIONAL_CONTROL`; phase control is removed. H1 tests Eψ/EΦ, H2 Phi feedback, H3 \(\Delta_A=A_{full}-A_{eta0}\) with lower paired-bootstrap CI above \(\max(.01,3\epsilon_{production,A})\), and H4 is eta-zero artifact identity for one-way psi. Each production error is space plus time error against N128/dt=.000625. Energy law applies only to eta-zero/full/sensitivity variational arms.

The manifest contains 184 unique conditions plus 9 replay attempts (193 total), all explicit. P0.5 remains a draft for final freeze review only.
