"""Transactional, policy-checked candidate execution.

The filesystem transaction prevents candidates from committing undeclared
project changes. It is not an operating-system security sandbox; untrusted code
still requires an external container or VM.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from fermion.hr.contracts import CandidateProgram, ExecutionResult, ProgramKind, ValidatorEvidence

from .observation import file_manifest
from .validators import ValidationContext, Validator


@dataclass(frozen=True)
class ExecutionPolicy:
    timeout_seconds: float = 10.0
    max_source_bytes: int = 100_000
    max_changed_artifacts: int = 32
    allowed_kinds: tuple[ProgramKind, ...] = (ProgramKind.PYTHON,)
    denied_python_imports: tuple[str, ...] = (
        "ctypes", "multiprocessing", "socket", "subprocess", "urllib", "requests", "winreg"
    )
    allow_irreversible: bool = False

    @classmethod
    def trusted_local(cls, timeout_seconds: float = 30.0) -> "ExecutionPolicy":
        """Opt-in policy for trusted code; use an external VM for untrusted code."""
        return cls(timeout_seconds=timeout_seconds,
                   allowed_kinds=(ProgramKind.PYTHON, ProgramKind.POWERSHELL),
                   denied_python_imports=(), allow_irreversible=True)


class PolicyViolation(ValueError):
    pass


class GuardedExecutor:
    def __init__(self, workspace: str | Path, policy: ExecutionPolicy | None = None):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace does not exist: {self.workspace}")
        self.policy = policy or ExecutionPolicy()

    def inspect(self, candidate: CandidateProgram) -> None:
        if candidate.kind not in self.policy.allowed_kinds:
            raise PolicyViolation(f"program kind is not enabled: {candidate.kind.value}")
        if len(candidate.source.encode("utf-8")) > self.policy.max_source_bytes:
            raise PolicyViolation("candidate source exceeds policy limit")
        if not candidate.reversible and not self.policy.allow_irreversible:
            raise PolicyViolation("irreversible candidate requires an explicit policy override")
        for artifact in candidate.declared_artifacts:
            self._safe_relative(artifact)
        if candidate.kind in (ProgramKind.PYTHON, ProgramKind.UNREAL_PYTHON):
            try:
                tree = ast.parse(candidate.source)
            except SyntaxError as error:
                raise PolicyViolation(f"invalid Python syntax: {error.msg}") from error
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = ([alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import)
                             else [(node.module or "").split(".")[0]])
                    denied = set(names) & set(self.policy.denied_python_imports)
                    if denied:
                        raise PolicyViolation(f"denied Python import: {sorted(denied)[0]}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {
                    "eval", "exec", "compile", "__import__"
                }:
                    raise PolicyViolation(f"denied Python call: {node.func.id}")

    def execute(self, candidate: CandidateProgram, validator: Validator, *, commit: bool = False) -> ExecutionResult:
        self.inspect(candidate)
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="fermion-transaction-") as temporary:
            stage = Path(temporary) / "workspace"
            shutil.copytree(self.workspace, stage, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".fermion"))
            before = file_manifest(stage, ignored=(".git", ".venv", "__pycache__", ".fermion"))
            command, script = self._command(candidate, stage)
            environment = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                           "TEMP": temporary, "TMP": temporary, "PYTHONNOUSERSITE": "1"}
            try:
                completed = subprocess.run(command, cwd=stage, capture_output=True, text=True,
                                           timeout=self.policy.timeout_seconds, env=environment)
                return_code, stdout, stderr, timed_out = completed.returncode, completed.stdout, completed.stderr, False
            except subprocess.TimeoutExpired as error:
                return_code, stdout, stderr, timed_out = None, error.stdout or "", error.stderr or "", True
            finally:
                script.unlink(missing_ok=True)
            after = file_manifest(stage, ignored=(".git", ".venv", "__pycache__", ".fermion"))
            changed = tuple(sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path)))
            declared = set(candidate.declared_artifacts)
            undeclared = tuple(path for path in changed if path not in declared)
            if len(changed) > self.policy.max_changed_artifacts:
                undeclared = tuple(sorted(set(undeclared) | set(changed)))
            context = ValidationContext(stage, return_code, stdout, stderr, changed, undeclared, timed_out)
            raw_evidence = validator.validate(context)
            execution_contradiction = float(bool(undeclared) or timed_out or return_code != 0)
            evidence = ValidatorEvidence(
                raw_evidence.success if not execution_contradiction else 0.0,
                raw_evidence.information,
                raw_evidence.goal_score,
                max(raw_evidence.contradiction, execution_contradiction),
                {**raw_evidence.details, "execution_safe": not bool(execution_contradiction)},
            )
            safe_success = evidence.success >= 0.5
            committed = bool(commit and safe_success)
            if committed:
                self._commit(stage, candidate.declared_artifacts)
            duration = time.perf_counter() - started
            return ExecutionResult(candidate.candidate_id, return_code, stdout, stderr, duration,
                                   timed_out, changed, undeclared, committed, not committed, evidence)

    def _command(self, candidate: CandidateProgram, stage: Path) -> tuple[list[str], Path]:
        if candidate.kind == ProgramKind.PYTHON:
            script = stage / ".fermion_candidate.py"
            script.write_text(candidate.source, encoding="utf-8")
            return [sys.executable, "-I", str(script)], script
        if candidate.kind == ProgramKind.POWERSHELL:
            script = stage / ".fermion_candidate.ps1"
            script.write_text(candidate.source, encoding="utf-8")
            return ["powershell", "-NoProfile", "-NonInteractive", "-File", str(script)], script
        raise PolicyViolation(f"no local executor for {candidate.kind.value}")

    def _safe_relative(self, relative: str) -> Path:
        target = (self.workspace / relative).resolve()
        try:
            return target.relative_to(self.workspace)
        except ValueError as error:
            raise PolicyViolation(f"artifact path escapes workspace: {relative}") from error

    def _commit(self, stage: Path, artifacts: tuple[str, ...]) -> None:
        for relative in artifacts:
            safe = self._safe_relative(relative)
            source, target = stage / safe, self.workspace / safe
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif target.exists():
                target.unlink()
