# First-party FERMiON module map

Vendor trees under `fermion/{bettercap,Ciphey,CL4R1T4S,codex,GhostTrack,hackingtool,spiderfoot,the-book-of-secret-knowledge}` are not first-party. This map covers the 112 first-party Python modules only.

## Package layers

```
CLI / dashboard / chat
        │
        ├── CognitiveRuntime          fermion/cognitive/runtime.py
        ├── FermionRuntime            fermion/cognitive/integration_runtime.py
        └── ApplicationControlPlane   fermion/control_plane.py
                │
                ├── adapters/*        typed ApplicationInterface
                └── software/kernel   execute / verify / checkpoint
                        │
                        └── hr/       frozen 193-param controller + trainer
```

### `fermion/hr/` — frozen controller

| Module | Role |
|---|---|
| `reference_193.py` | Canonical 193-parameter specimen. Do not change dims/order without FORMAT_VERSION. |
| `system.py` | `FermionHR`: encoder → recursive core → router → hybrid transition → 7-term energy. |
| `contracts.py` | `CandidateProgram`, `HRState`, `ValidatorEvidence`, `ExecutionResult`. |
| `encoders.py` | Multimodal encoder with availability masks. |
| `recursive_core.py` | Three shared refinement passes; ψ / h / m / e. |
| `routing.py` | Evidence-grounded candidate ranking. |
| `transition.py` | Hybrid discrete/symplectic next-state. |
| `energy.py` / `uncertainty.py` | Diagnostic energy; ensemble effect variance. |
| `memory.py` / `checkpoint.py` / `trainer.py` | SQLite episodic memory, strict checkpoints, offline trainer. |
| `ablations.py` / `diagnostics.py` / `config.py` | Ablations, traces, `HRConfig`. |

Consumed by: curriculum, software kernel, `python -m fermion reference`. Isolated from AI-G1 by design.

### `fermion/software/` — learning kernel

| Module | Role |
|---|---|
| `application.py` | `ApplicationInterface` protocol; dummy adapter; audit log. |
| `kernel.py` | Rank → execute → validate → record. |
| `executor.py` | `GuardedExecutor`: AST policy, disposable copy, declared-artifact commit. |
| `validators.py` | Exit code / file / JSON validators. LLM opinion is never evidence. |
| `ownership.py` | Fail-closed `OwnershipGate` before mutating actions. |
| `observation.py` / `replay.py` / `recorder.py` | Observation bus, replay DB, demonstrations. |
| `skill_acquisition.py` / `ui_skill_acquisition.py` / `skills.py` | Skill extract/validate; GSE UI hooks (provisional). |
| `learning_manager.py` / `diagnostic_transition.py` | Goals; GSE diagnostic engine. |
| `safe_self_evolver.py` | Legacy evolver. Not the CLI target (`fermion.safe_self_evolver` is). |
| `windows.py` / `interfaces.py` / `capabilities.py` / `actions.py` / `outcomes.py` | Win32/UI ranking helpers. |

### `fermion/cognitive/` — conversational loop

| Module | Role |
|---|---|
| `runtime.py` | Chat orchestration; control-plane bridge; bounded proofs. |
| `runtime_bootstrap.py` | Manifest + gates + provenance composition root. |
| `integration_runtime.py` | `FermionRuntime.plan` / `authorize`. |
| `integration_registry.py` | First-party SHA-256 manifest; append-only provenance. |
| `network.py` / `workspace.py` / `memory.py` | Recurrent PyTorch state; global workspace; SQLite memory. |
| `llm.py` | Local GGUF cortex via llama.cpp adapter. |
| `scientific_routing.py` / `chemistry.py` / `engineering.py` / `science.py` / `computation.py` | Deterministic oracles + receipts. |
| `evidence.py` / `evidence_grounding.py` | Execution/memory/web receipts; claim validator. |
| `scientific_gates.py` / `scientific_ir.py` | Artifact-backed gates; IR migration. |
| `capability_registry.py` | Read-only live capability inspection. |
| `tool_bridge.py` / `agent_bridge.py` | Qwen plan parse; pydantic-ai synthesis. |
| `bounded_execution.py` | GuardedExecutor proofs (no `runtime.py` subprocess). |
| `test_receipt.py` | Isolated pytest + receipt. |
| `release_*.py` / `reproducibility.py` / `web_research.py` / `skills.py` / `discovery.py` | Release, bundles, URL fetch, SKILL.md discovery, GGUF scan. |

### `fermion/adapters/` — control-plane applications

Registered in `default_control_plane`: notepad_sandbox, coding_sandbox, self_evolver, nmap_reports (offline XML), local_programs, imhex (read-only), internet, llama_runtime, fermion_science, vendor_inventory, ciphey (local decode only), bettercap/hackingtool/ghosttrack/spiderfoot/codex (status/catalog inspect; live launch refused).

Present but unregistered: `unreal.py`, live Notepad UI (`notepad_ui.py`). Llama generate stays CLI-only.

### `fermion/ai_g1/` — isolated spectral track

Does not import `FermionHR193` except as a frozen hash in the P1.1 source manifest. `ai_g2s.py` has `spectral_utility_gate` (no promotion). `ai_g2s_r1.py` is execution infrastructure without a full-benchmark command. `ai_g2s_provenance.py` is verify-only.

### `fermion/cp10/` — gated scientific protocol

`oracle_a_launcher_p0_10.verify` is the live CLI target. `runner.full` exits without a launch record. `frozen_protocol` / `_core` still pin P0.8 hashes for R1 source tests. See `docs/CP10_VS_AI_G2S.md`.

### Roots

| Path | Role |
|---|---|
| `fermion/__main__.py` | CLI. |
| `fermion/control_plane.py` | Plan parse/validate/execute. |
| `fermion/curriculum.py` | Six-stage HR curriculum. |
| `fermion/dashboard.py` | Localhost whitelist console + OpenClaw bridge. |
| `fermion/task.py` | JSON task spec runner. |
| `fermion/safe_self_evolver.py` | Canonical evolver. |
| `fermion/source_exclusions.py` | Vendor directory names. |
| `fermion_symplectic_dysib.py` | DySIB benchmark; `fermion/research/` re-exports it. |

## Test map (first-party `tests/`)

HR/reference, software kernel, adapters, cognitive runtime, chemistry/engineering, gates, CP10 P0.8/P0.10 verify, AI-G2S provenance/R1, control plane, dashboard. Live Windows UI tests are marked `windows_ui` and deselected by default.
