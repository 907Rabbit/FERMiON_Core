"""Load and execute a declarative Software Learning Kernel task."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hr.contracts import CandidateProgram, ProgramKind
from .hr.memory import EpisodicMemory
from .hr.system import FermionHR
from .software.executor import ExecutionPolicy, GuardedExecutor
from .software.kernel import KernelResult, SoftwareLearningKernel
from .software.observation import FileSystemProvider, ObservationBus
from .software.replay import ReplayDatabase
from .software.validators import CompositeValidator, ExitCodeValidator, FileExistsValidator, JSONValidator, Validator


@dataclass(frozen=True)
class TaskRun:
    selected_id: str
    success: float
    committed: bool
    changed_artifacts: tuple[str, ...]
    undeclared_artifacts: tuple[str, ...]
    explanation: str


def load_task(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("goal"), str):
        raise ValueError("task spec requires a string goal")
    if not isinstance(value.get("candidates"), list) or not value["candidates"]:
        raise ValueError("task spec requires a nonempty candidates array")
    return value


def run_task(path: str | Path, *, commit: bool = False) -> TaskRun:
    spec = load_task(path)
    workspace = Path(spec.get("workspace", Path(path).parent)).resolve()
    state_dir = workspace / ".fermion"; state_dir.mkdir(parents=True, exist_ok=True)
    candidates = [_candidate(item) for item in spec["candidates"]]
    policy = ExecutionPolicy(timeout_seconds=float(spec.get("timeout_seconds", 10.0)))
    kernel = SoftwareLearningKernel(FermionHR(), ObservationBus([FileSystemProvider(workspace)]),
                                    GuardedExecutor(workspace, policy),
                                    ReplayDatabase(state_dir / "replay.db"),
                                    EpisodicMemory(state_dir / "memory.db"))
    result = kernel.run(spec["goal"], candidates, _validator(spec.get("validator", {"type": "exit_code"})),
                        commit=commit)
    from .hr.diagnostics import explain_decision
    return TaskRun(result.execution.candidate_id, result.execution.validator.success,
                   result.execution.committed, result.execution.changed_artifacts,
                   result.execution.undeclared_artifacts, explain_decision(result.decision))


def _candidate(value: dict[str, Any]) -> CandidateProgram:
    return CandidateProgram(str(value["id"]), str(value["source"]),
                            ProgramKind(value.get("kind", "python")),
                            tuple(float(item) for item in value.get("features", ())),
                            tuple(value.get("declared_artifacts", ())),
                            float(value.get("estimated_cost", 0.0)), float(value.get("estimated_risk", 0.0)),
                            bool(value.get("reversible", True)), str(value.get("provenance", "task-spec")),
                            dict(value.get("metadata", {})))


def _validator(value: dict[str, Any]) -> Validator:
    kind = value.get("type")
    if kind == "exit_code":
        return ExitCodeValidator()
    if kind == "file_exists":
        return FileExistsValidator(value["path"], nonempty=bool(value.get("nonempty", True)))
    if kind == "json":
        return JSONValidator(value["path"], tuple(value.get("required_keys", ())),
                             dict(value.get("expected", {})), float(value.get("tolerance", 1e-8)))
    if kind == "composite":
        return CompositeValidator([_validator(child) for child in value["validators"]],
                                  bool(value.get("require_all", True)))
    raise ValueError(f"unknown validator type: {kind}")
