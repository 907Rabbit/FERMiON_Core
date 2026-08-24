# FERMiON

FERMiON is an experimental, evidence-grounded software-learning and research
controller. It ranks candidate programs, executes them transactionally, validates
their real effects, and learns only from structured validator evidence.

It is a research implementation, not a claim of general intelligence or
consciousness. The local executor protects the project through disposable copies
and declared-artifact commits; it is not an OS security sandbox. Run genuinely
untrusted programs in a container or VM.

## Implemented system

- Canonical, frozen 193-parameter FERMiON-HR regression specimen
- Configurable multimodal encoder with explicit availability masks
- Three-pass shared recursive inference and separate ψ, h, m, and e states
- Hybrid discrete/symplectic transition model
- Ensemble effect uncertainty and seven-term diagnostic energy
- Evidence-grounded candidate router and offline trainer
- SQLite episodic memory, replay database, strict checkpoints, and diagnostics
- Observation bus, demonstration recorder/compiler, and capability registry
- Transactional Python execution with static policy checks and exact validators
- Optional accessibility, screenshot, CLI, llama.cpp, and Unreal adapters
- Six-stage curriculum with advancement/falsification results
- Phase 17B.2 single-to-double-pendulum Symplectic DySIB benchmark
- Persistent conversational cognitive runtime with a recurrent PyTorch state, typed SQLite memory, workspace broadcast, self-model, metacognition, and calculated functional-access metrics

## Local cognitive CLI

The cognitive runtime follows the explicit pipeline **language interpretation → FERMiON cognitive processing → language response**. It does not download or depend on a cloud model. Local GGUF discovery only scans the configured Windows-friendly paths.

```powershell
python -m fermion models
python -m fermion --model "G:\models\model.gguf" chat
python -m fermion chat --once "Remember that my experimental coefficient alpha is 0.37."
python -m fermion chat --once "What coefficient did I use?"
python -m fermion cognition
```

In interactive mode, use `/cognition`, `/checkpoint save NAME`, `/checkpoint load NAME`, and `/quit`. State, SQLite memory, and checkpoints live under `.fermion_cognitive`; provenance is appended to `logs/cognition.jsonl`.

`python -m fermion --disable-cognition chat` provides the requested ablation: the response path runs without recurrent state or memory integration updates. Existing llama.cpp lifecycle commands remain available under `python -m fermion llama ...`.

FERMiON's conscious-access metrics measure functional integration, recurrence, global availability, self-modeling, and related computational properties. They are not evidence by themselves of phenomenal consciousness.

For Qwen Thinking models, the local language-cortex boundary separates text before the final `</think>` marker from the user-visible answer. Internal thought is never printed; an incomplete generation falls back to FERMiON's prepared answer. Qwen's response budget and timeout are set in `fermion.local.json`.

## Evidence verification

Execution and semantic-memory claims are backed by immutable receipts created by the local executor or SQLite store, then appended to `logs/receipts.jsonl`. Qwen cannot generate receipt IDs or tool outcomes. In the interactive CLI use `/evidence last`, `/execution verify EVIDENCE_ID`, and `/memory verify KEY`; an unavailable or pre-receipt record reports `VERIFICATION_FAILED`.

The interface order is native API/CLI, accessibility, then vision-driven GUI.

## Verify

On Windows:

```powershell
cd C:\Users\kausi\Desktop\AI\MyAIproject
.\.venv\Scripts\python.exe -m pytest -q
```

Inspect the frozen reference model:

```powershell
.\.venv\Scripts\python.exe -m fermion reference
```

Run the local curriculum. Stages requiring llama.cpp or Unreal are explicitly
skipped until configured; failed experimental gates remain visible.

```powershell
.\.venv\Scripts\python.exe -m fermion curriculum
```

## Linked llama.cpp runtime

The ignored local configuration `fermion.local.json` links the official llama.cpp b10233 Windows CPU build
to the existing CodeLlama 7B Instruct Q4_K_S GGUF. The context and batch sizes
are intentionally small because this machine has limited available RAM.

```powershell
.\.venv\Scripts\python.exe -m fermion llama status
.\.venv\Scripts\python.exe -m fermion llama start
.\.venv\Scripts\python.exe -m fermion llama test
.\.venv\Scripts\python.exe -m fermion llama stop
```

Run the local-LLM curriculum stage while the server is healthy:

```powershell
.\.venv\Scripts\python.exe -m fermion curriculum --with-llama
```

The server binds only to `127.0.0.1`. Runtime settings and absolute local paths
are in `fermion.local.json`; logs and the PID file are under `.fermion/`. A local
bearer key protects completion requests; neither the key nor runtime state is
tracked by Git.

Run the Symplectic DySIB benchmark:

```powershell
.\.venv\Scripts\python.exe -m fermion symplectic --quick
```

## Execute a validated task

Create a task JSON such as:

```json
{
  "goal": "Create result.json containing the answer",
  "workspace": "C:/path/to/a/project",
  "candidates": [
    {
      "id": "write-answer",
      "source": "import json\njson.dump({'answer': 42}, open('result.json', 'w'))",
      "declared_artifacts": ["result.json"],
      "estimated_cost": 0.1,
      "estimated_risk": 0.1
    }
  ],
  "validator": {
    "type": "json",
    "path": "result.json",
    "required_keys": ["answer"],
    "expected": {"answer": 42}
  }
}
```

Test it transactionally without changing the real workspace:

```powershell
.\.venv\Scripts\python.exe -m fermion run-task task.json
```

Add `--commit` to copy only declared artifacts back after successful validation.

## Scientific status

The architecture is implemented and testable, but its learned routing quality is
not yet validated. Current synthetic curriculum results are allowed to fail by
design. External Stage 5 and Stage 6 evaluation require a configured llama.cpp
model and Unreal installation. Symplectic DySIB promotion requires repeated
seeds and held-out initial-condition families; one quick run is not evidence of
general superiority.
