# FERMiON Integration Bootstrap — Phase 1 Inspection

**Scope:** `G:\MyAIproject`  
**Audit time:** 2026-08-24 (local workstation)  
**Mode:** inspection-only, except for writing this requested report. No scientific
runner, training job, dashboard action, local-model action, email, system
configuration, or external service was started or changed by this audit.

## Executive result

FERMiON is a locally runnable Python research/control project with a canonical
193-parameter HR reference, separate AI-G1/AI-G2/AI-G2S experimental tracks, a
cognitive runtime, an adapter/control-plane layer, and a localhost-only dashboard.
The strongest durable scientific evidence found is **pre-execution provenance and
regression evidence** for AI-G2S P1.1—not a completed paired experiment. The
full AI-G2S matrix remains gated and the available partial checkpoints are not
scientific results.

The root Git repository has no commits and every listed project item is
untracked. This prevents any claim that the present tree is a committed frozen
baseline. Eight nested Git repositories are also present beneath `fermion/`;
they must be treated as vendored/independent material, not automatically as
FERMiON runtime components.

## Active workspace instructions

| Path | Scope / status |
|---|---|
| `G:\MyAIproject\AGENTS.md` | Active for this workspace and all first-party project paths; read for this audit. It requires non-destructive handling and an existing-solutions preflight. |
| `G:\MyAIproject\.openclaw_agent\AGENTS.md` | Active only for the OpenClaw agent workspace. It constrains Crestodian to return FERMiON bridge proposals rather than malformed native tool calls. |
| `G:\MyAIproject\fermion\bettercap\AGENTS.md` | Applies only below the vendored `bettercap` tree; not active for FERMiON Python changes. |
| `G:\MyAIproject\fermion\codex\AGENTS.md` and `...\codex-rs\tui\src\bottom_pane\AGENTS.md` | Apply only below the nested Codex tree; not active for FERMiON Python changes. |
| `.venv\Lib\site-packages\pydantic_ai\...\AGENTS.md` | Dependency-local instructions; not active for project source. |

`BOOTSTRAP.md` is present at the root. It was neither acted on nor removed,
because this phase prohibits modification/deletion and the user requested an
inspection only.

## Repository inventory

### First-party runtime and science modules

| Area | Exact paths | Observed role |
|---|---|---|
| Entry points | `fermion\__main__.py`, `README.md`, `pyproject.toml` | CLI: reference, curriculum, Symplectic DySIB, task runner, llama lifecycle, dashboard, self-evolver, cognitive chat/models/checkpoints. |
| Frozen HR core | `fermion\hr\reference_193.py`, `config.py`, `contracts.py`, `encoders.py`, `recursive_core.py`, `transition.py`, `energy.py`, `memory.py`, `uncertainty.py`, `routing.py`, `system.py`, `checkpoint.py`, `trainer.py`, `ablations.py`, `diagnostics.py` | Canonical FERMiON-HR reference and supporting system/training architecture. |
| AI-G1 / AI-G2 / AI-G2S | `fermion\ai_g1\core.py`, `spectral.py`, `diagnostics.py`, `ai_g2.py`, `ai_g2s.py`, `ai_g2s_r1.py` | Separate experimental learning track. `spectral.py` contains `GaussianSpectralOracle` and learnable spectral field code. |
| Cognitive runtime | `fermion\cognitive\runtime.py`, `workspace.py`, `memory.py`, `llm.py`, `agent_bridge.py`, `tool_bridge.py`, `capability_registry.py`, `evidence*.py`, `scientific_ir.py`, `scientific_routing.py`, `web_research.py`, `skills.py` | Persistent state/memory, evidence, model routing, typed tool bridging, scientific IR/routing. |
| Software-learning kernel | `fermion\software\kernel.py`, `executor.py`, `validators.py`, `learning_manager.py`, `observation.py`, `replay.py`, `recorder.py`, `ownership.py`, `diagnostic_transition.py`, `ui_skill_acquisition.py` | Transactional candidate execution, validators, replay/observation and GSE diagnostic hooks. |
| Control plane and UI | `fermion\control_plane.py`, `fermion\dashboard.py` | Registry, plan validation, audit/checkpoint/rollback, and local dashboard. The dashboard binds only to `127.0.0.1` or `localhost`. |
| Adapters | `fermion\adapters\{coding,imhex,internet,llama_cpp,local_program,nmap_reports,notepad,notepad_curriculum,notepad_ui,self_evolver,unreal}.py` | Bounded interfaces for local applications, offline reports, web data, and model/runtime integrations. |

### Components requested by name

| Requested component | Artifact-supported finding |
|---|---|
| Frozen 193-parameter reference | `fermion\hr\reference_193.py`; current SHA-256 verified as `8F544FCE6F0E7A03D52A9CBC46B366D0B9F82404B952CF479126CCA9D1EEF953`. The repaired AI-G2S source manifest records the same value. |
| FERMiON-HR / multimodal | HR modules above; README describes the configurable multimodal encoder and availability masks. No separate saved multimodal training artifact was found in `artifacts/`. |
| MFE / PhiLang / Psilang | No first-party module or durable artifact matching these names was found by static term search. They are therefore **not mapped to an implemented component** in this tree. |
| GSE | `fermion_symplectic_dysib.py` plus `fermion\software\diagnostic_transition.py` (`GSEDiagnosticEngine`) and `ui_skill_acquisition.py` (`GSENullPrincipleAblation`). A GSE-vs-baseline helper is also in `adapters\notepad_ui.py`. No gate result was found that proves scientific utility. |
| Gaussian | AI-G1 `GaussianSpectralOracle` in `fermion\ai_g1\spectral.py`; Gaussian pH-residual likelihood appears in cognitive chemistry. These are code constructs, not verification of the user-provided theoretical action. |
| CP10 / CP11 | No `CP10`/`CP11`-named code gates were found. The closest durable artifacts are `configs\ai_g2s_p1_0.json` and `configs\ai_g2s_p1_1.json`, with P1.0/P1.1 hashes recorded as protocol controls. |
| AI-G1 | Source and tests exist. No standalone final artifact was located. |
| AI-G2 | `artifacts\ai_g2_results.json` has three seed records and an embedded SHA field, but no detached checksum file was found; its claimed metrics are artifact data, not independently re-run here. |
| AI-G2S | P1.0 coverage records blockers; P1.1 provides protocol, source manifests, smoke/regression evidence, launch-readiness/audit records, and partial checkpoints. Full paired execution is explicitly gated. |
| LM Studio / local LLM | `fermion.local.json` targets a local `127.0.0.1:1234` completion endpoint and records a Qwen GGUF path under `F:\models`. `adapters\llama_cpp.py` owns llama.cpp lifecycle. No model was started or queried. |
| OpenClaw / Crestodian | `.openclaw_agent\AGENTS.md` supplies text-protocol bridge rules. `dashboard.py` has an OpenClaw bridge which validates a proposal via the control plane; it is not evidence that native OpenClaw tools are healthy. |
| Computer operation | `notepad_sandbox`, `coding_sandbox`, and `local_programs` are registered. Mutations use typed calls and control-plane approval gates/checkpoints. |
| Internet / email / memory / tools | Internet adapter supports bounded search/fetch and verified non-executing download. No email adapter/connector was found. Cognitive SQLite memory is at `.fermion_cognitive\memory.sqlite3`; receipts/logs are under `logs\`. Capability/evidence/tool bridge modules exist. |

### Nested repositories and non-runtime material

Nested Git repositories were found at `fermion\bettercap`, `Ciphey`, `CL4R1T4S`,
`codex`, `GhostTrack`, `hackingtool`, `spiderfoot`, and
`the-book-of-secret-knowledge`. They are not declared by the top-level Python
package configuration and should be isolated from any unified runtime by default.
Several contain security/networking tooling, third-party prompt archives, or
other unrelated source trees. Their presence is a supply-chain and scope-boundary
concern, not a licence to expose their capabilities to FERMiON.

## Architecture and data flow

```text
Perception / inputs
  CLI chat, documents, workspace state, local adapters, user-supplied reports
       |
       v
Cognitive workspace + SQLite memory + evidence / reproducibility records
       |
       v
Reasoning and planning
  scientific IR/routing, capability registry, LLM boundary, candidate router
       |
       v
Model / tool selection
  HR reference | AI-Gx experiment | local LLM | registered control-plane app
       |
       v
Authorization boundary
  Control-plane schema validation -> approval requirement -> checkpoint
       |
       v
Authorized action
  typed adapter operation only; dashboard is localhost-only
       |
       v
Validation, audit, rollback and provenance
  validator outcome -> audit receipt/log -> SQLite/JSON/checkpoint evidence
```

The required integration gap is an explicit shared state/provenance contract
between the cognitive runtime, scientific experiment tracks, and control plane.
At present these pieces coexist but their cross-track promotion semantics are
not established by a single runtime manifest.

## Frozen versus experimental boundary

| Boundary | Evidence | State |
|---|---|---|
| HR-193 reference | Source hash matches repaired P1.1 manifest. | **Frozen reference byte verified.** |
| AI-G2S P1.0 | `protocol_coverage.json` declares the runner blocked, smoke not started, final evaluation not started. | **Blocked / superseded as incomplete.** |
| AI-G2S P1.1 pre-execution | Config, source manifests, environment, smoke and regression artifacts exist; detached provenance and repaired authorization hashes verify. | **Pre-execution evidence present.** |
| AI-G2S P1.1 full paired experiment | Authorization record says `READY_FOR_EXPLICIT_USER_AUTHORIZATION_ONLY`; no final predictions. | **Gated; not launched by this audit.** |
| Partial AI-G2S files | `artifacts\ai_g2s_p1_1_full\run.log` says run failed; progress record identifies a transient checkpoint at step 100 and `test_data_accessed:false`. | **Failed/incomplete; not a result.** |
| AI-G2 results | JSON contains three seeds and self-reported metrics. | **Experimental artifact, not independently verified in Phase 1.** |
| Self-evolution | Two implementations: `fermion\safe_self_evolver.py` and `fermion\software\safe_self_evolver.py`; adapter targets a bounded workspace. | **Experimental; interface duplication requires resolution.** |
| Cognitive data | SQLite memory/checkpoint/log files exist. | **Mutable runtime state; not a frozen scientific baseline.** |

## Hashes and test evidence

### Hash verification performed now

| Target | Result |
|---|---|
| `artifacts\ai_g2s_r1_1\preexecution_provenance_manifest.json` | Recorded and computed SHA-256 match: `8FF292C7D4D26C7A3F6B49115537F7CAFE32AA6DCCDFFE004407C5FC3CBA95CA`. |
| `artifacts\ai_g2s_r1_1_repaired\launch_authorization_record.json` | Recorded and computed SHA-256 match: `7DE1433D41E2E11B5999CF14AC32BF3525A0800E60654FD1F8B5648A4D8B3E8B`. |
| `artifacts\ai_g2s_r1_1_repaired\preexecution_provenance_manifest.json` | Recorded and computed SHA-256 match: `595F74D8A1B41A03061107A076E5841FE8C1B4DE9AF05878E9142D6160A270EB`. |
| `fermion\hr\reference_193.py` | Computed SHA-256: `8F544FCE6F0E7A03D52A9CBC46B366D0B9F82404B952CF479126CCA9D1EEF953`; it equals the value in repaired P1.1 source manifest. |

### Test/validation status

No test suite was run in this phase, by request to avoid executing runners.
Recorded (not re-executed) evidence is:

| Artifact | Recorded result | Interpretation |
|---|---|---|
| `artifacts\ai_g2s_r1_1\regression_final.json` | `226 passed, 1 deselected in 36.14s` | Historical regression record only. |
| `artifacts\ai_g2s_r1_1_repaired\launch_readiness_audit.json` | `229 passed, 1 deselected` | Historical repaired-regression assertion only. |
| Static AST parse performed in this audit | 87 first-party Python files, 0 syntax failures. | Syntax-only check; it does not prove imports, runtime behavior, or scientific correctness. |

## Capability and access matrix

| Capability | Interface | Authority / guard | Phase-1 action |
|---|---|---|---|
| HR reference / curriculum / Symplectic | CLI | User-initiated local execution | Not run. |
| AI-G2S full experiment | PowerShell launcher | Explicit launch authorization; source/config hash checks; final-test gate | Not run. |
| Local LLM | llama.cpp adapter + local endpoint | Localhost config; model lifecycle controls | Not started or queried. |
| OpenClaw | Text bridge to dashboard | Schema validation; execution explicit at bridge call | Not contacted. |
| Web | Internet adapter | Bounded public HTTP; untrusted data; verified SHA required for download | Not used. |
| Nmap/NSE | Offline XML report adapter | User-provided XML only; no scan/NSE/shell/network probe execution | Not used. |
| Files/code | Notepad/coding sandboxes | Typed operations, approval for mutation, checkpoints | Not used. |
| Programs | Local program catalog | Registration and launch are mutating/approved | Not used. |
| Email | None discovered | No configured connector found | Not accessed. |
| Memory/provenance | SQLite, JSONL, checkpoints | Local mutable state; receipts/evidence modules | Read only for inventory. |

## Issues, duplicates, gaps, and uncertainties

1. **Uncommitted root:** `git status --short` lists the entire project as
   untracked and `git log` reports no commit on `master`. Establishing a
   reviewed baseline commit and manifest is prerequisite to a trustworthy
   frozen-versus-experimental boundary.
2. **Large nested repository contamination:** eight nested repositories add
   9,000+ files below `fermion/`, including unrelated security tooling. The
   top-level package has no explicit vendor allowlist or isolation manifest.
3. **Self-evolver duplication:** `fermion\safe_self_evolver.py` and
   `fermion\software\safe_self_evolver.py` are separate implementations.
   The root `safe_self_evolver.py` is a convenience wrapper for the latter,
   while the control-plane adapter uses the former. This is a material
   interface/provenance ambiguity.
4. **AI-G2S state:** P1.0 is documented as incomplete; P1.1 is pre-execution
   ready but unearned. The partial run failed and must not be resumed or
   interpreted without a separately authorized recovery decision.
5. **Term mismatch:** MFE, PhiLang, Psilang, CP10 and CP11 were not found as
   implemented first-party names. Mapping them into the runtime would require
   a specification, tests, and a declared track—none should be inferred.
6. **Documentation staleness:** README's Windows path is
   `C:\Users\kausi\Desktop\AI\MyAIproject`, not this active workspace, and
   its rendered text displays encoding artifacts in this shell. Documentation
   needs a Phase-2, reviewed correction rather than silent edits.
7. **Import status uncertainty:** syntax was statically parsed, but dynamic
   import health was intentionally not checked because it may execute import
   side effects. No broken import is asserted either way.
8. **No final test rerun:** recorded pytest results are not current run
   evidence. A future test phase needs isolated `G:\tmp` basetemps and a
   declared scope.

## Prioritized Phase-2 integration plan (proposal only)

1. **Baseline and isolation first.** Create a reviewed root manifest covering
   first-party source, frozen HR-193, allowed artifacts, nested repositories,
   and ignored runtime folders. Do not include mutable databases/logs or
   third-party trees in the scientific baseline.
2. **Define an immutable cross-track provenance schema.** One versioned record
   should identify run/plan ID, source/config/environment hashes, seed,
   dataset split, authority, evidence receipts, artifact hashes, and promotion
   decision. It should be appended by the control plane and consumed read-only
   by cognitive/runtime views.
3. **Resolve self-evolver ownership.** Select one implementation as the
   canonical bounded engine; specify migration/compatibility tests and archive
   the other under a distinct experimental namespace. Do not merge their audit
   histories.
4. **Implement a narrow runtime façade.** Define explicit interfaces:
   `PerceptionEvent -> WorkspaceState -> Plan -> AuthorizedAction ->
   ValidationReceipt -> ProvenanceRecord`. Adapt HR, cognitive, AI-Gx and
   control-plane modules behind it without coupling frozen science to mutable
   LLM state.
5. **Keep scientific gates separate.** Add an auditable registry marking
   `HR-193=frozen`, `AI-G2S-P1.0=blocked`,
   `AI-G2S-P1.1=preexecution/gated`, and all GSE/CP/MFE claims as provisional
   unless a durable gate artifact says otherwise.
6. **Add integration tests after the schema exists.** Test no test-split access
   before selection, hash mismatch hard-failure, rollback/audit behavior,
   unknown tool rejection, and adapter scope boundaries. Run only after the
   user authorizes Phase 2.
7. **Defer consequential actions.** No launch of the 90-condition AI-G2S
   matrix, OpenClaw gateway change, model server, external network request,
   or system configuration change is included in this plan.

## Recommended next authorization

**Registry/provenance extension** is the highest-value next step: add the
immutable cross-track registry and first-party manifest only, with no
scientific runner launch and no external service changes. This resolves the
largest present risk—provenance ambiguity—before any AI-G2S, GSE, or
self-evolution action.

## Commands run

```powershell
Get-ChildItem -LiteralPath G:\MyAIproject ...; git -C G:\MyAIproject status --short; git -C G:\MyAIproject rev-parse --is-inside-work-tree; git -C G:\MyAIproject log -1 --oneline
Get-Content README.md; Get-Content pyproject.toml; Get-ChildItem ... -Recurse -File
Get-Content selected artifacts/configs/fermion.local.json; Get-FileHash -Algorithm SHA256 selected targets
Select-String first-party source for architecture, gates, adapters and term mapping
python -c "ast.parse(...)"  # 87 first-party Python files, syntax only
```

## Report integrity

The whole-file SHA-256 is reported in the completion message. Embedding a
whole-file digest inside the file would change that digest; this report therefore
uses the externally reported post-write value as its integrity identifier.
