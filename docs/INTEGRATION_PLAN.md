# FERMiON remaining integration

Leave all `.pytest-*` directories in place. They are not part of this work.

FERMiON is integrated when a component is reachable through an existing first-party
seam: the control plane, cognitive chat, the verified composition root, the CLI
or dashboard, the capability registry, or scientific gates. New tools implement
`ApplicationInterface` and are registered on `default_control_plane`. Vendor
trees under `fermion/` stay excluded from first-party manifests and are not
executable adapters.

## Runtime split (what this wiring closes)

- `CognitiveRuntime` is the chat path. It previously executed two hardcoded
  Python proofs with a private `subprocess` and did not call the control plane.
- The dashboard `/agent` and `/api/bridge` paths already validated typed plans.
- `FermionRuntime` / `load_verified_runtime` verified manifests and gates but
  was unused by chat.

These paths now share `default_control_plane` construction. Chat parses JSON or
`fermion_plan` markup as a proposal. Mutating plans require approval. Documented
prime/workspace proofs run through `GuardedExecutor`, not `runtime.py`
subprocess.

## Vendor posture

`bettercap`, `hackingtool`, `GhostTrack`, `spiderfoot`, `Ciphey`, `CL4R1T4S`,
`codex`, and `the-book-of-secret-knowledge` are inventory-only. The
`vendor_inventory.list_excluded` operation reports that fact. Live attack,
scan, tracking, or competing-agent wrapping is not registered.

`God's Eye View` is excluded from first-party source hashes and is registered
as `gods_eye_view`: localhost-only start/stop/open. FERMiON does not proxy its
feeds or treat globe output as authority.

`local_programs.register_program` rejects executables whose path contains an
excluded vendor directory name.

## Scientific gates

CP10 and AI-G2S remain verify-only. Oracle-A/B trajectories, held-out seeds,
bootstrap inference, a CP10 verdict, CP11, and the full AI-G2S paired matrix
are not control-plane operations.
