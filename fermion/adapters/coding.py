"""Typed source-file and approved process control for the FERMiON coding sandbox."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


@dataclass(frozen=True)
class CodingSandboxConfig:
    sandbox_root: Path
    allowed_roots: tuple[Path, ...]
    editor_executable: Path = Path(r"C:\Windows\System32\notepad.exe")
    launch_enabled: bool = False
    execution_root: Path | None = None
    execution_timeout_seconds: int = 120


class CodingSandboxAdapter(ApplicationInterface):
    """Edit approved files and run explicitly approved argv-based processes."""

    _CAPABILITIES = (
        CapabilityDefinition("inspect_file", False, True, "Read a source or text file."),
        CapabilityDefinition("create_file", True, True, "Create a source or text file."),
        CapabilityDefinition("append_text", True, False, "Append text to a source or text file."),
        CapabilityDefinition("replace_text", True, True, "Replace complete source or text file content."),
        CapabilityDefinition("rename_file", True, True, "Rename a source or text file."),
        CapabilityDefinition("delete_file", True, True, "Delete a source or text file."),
        CapabilityDefinition("open_in_editor", False, True, "Open a file in the configured editor; never run it."),
        CapabilityDefinition("run", False, False, "Run an approved command in the configured workspace."),
    )
    _TEXT_EXTENSIONS = frozenset({
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".html", ".htm", ".css",
        ".cs", ".c", ".h", ".cpp", ".hpp", ".java", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
        ".ps1", ".sh", ".bat", ".cmd", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".sql",
    })

    def __init__(self, config: CodingSandboxConfig) -> None:
        self.config = config
        self.root = config.sandbox_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.roots = tuple(dict.fromkeys(root.resolve() for root in config.allowed_roots))
        if not self.roots:
            raise ValueError("coding sandbox requires at least one allowed root")
        if not config.editor_executable.is_file():
            raise ValueError(f"editor executable not found: {config.editor_executable}")
        execution_root = config.execution_root or self.root
        self.execution_root = execution_root.resolve()
        if not any(self.execution_root == root or self.execution_root.is_relative_to(root) for root in self.roots):
            raise ValueError("execution root must be inside a configured coding root")
        if not self.execution_root.is_dir():
            raise ValueError("execution root must be an existing directory")
        if isinstance(config.execution_timeout_seconds, bool) or not isinstance(config.execution_timeout_seconds, int):
            raise ValueError("execution timeout must be an integer")
        if not 1 <= config.execution_timeout_seconds <= 300:
            raise ValueError("execution timeout must be between 1 and 300 seconds")
        self._last_state: dict[str, Any] = {"last_path": None, "last_sha256": None}
        self._checkpoints: dict[str, dict[str, bytes | None]] = {}
        self._active_checkpoint: str | None = None

    def _path(self, value: Any) -> Path:
        candidate = Path(str(value))
        path = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if path.suffix.lower() not in self._TEXT_EXTENSIONS or not any(path.is_relative_to(root) for root in self.roots):
            raise ValueError("files must be supported text/source files inside configured coding roots")
        return path

    @staticmethod
    def _digest(value: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()

    def _snapshot(self, *paths: Path) -> None:
        if self._active_checkpoint is None:
            return
        snapshots = self._checkpoints[self._active_checkpoint]
        for path in paths:
            snapshots.setdefault(str(path), path.read_bytes() if path.exists() else None)

    def _remember(self, path: Path) -> None:
        if path.exists():
            self._last_state = {"last_path": str(path), "last_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def _command(self, value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or not 1 <= len(value) <= 64:
            raise ValueError("command must be a JSON list containing 1 to 64 arguments")
        command: list[str] = []
        for argument in value:
            if not isinstance(argument, str) or not argument or "\x00" in argument:
                raise ValueError("every command argument must be a nonempty string without NUL bytes")
            command.append(argument)
        if sum(len(argument) for argument in command) > 16_384:
            raise ValueError("command exceeds the 16,384-character limit")
        return tuple(command)

    def _working_directory(self, value: Any) -> Path:
        if value is None:
            return self.execution_root
        if not isinstance(value, str) or not value.strip():
            raise ValueError("cwd must be a nonempty workspace path")
        candidate = Path(value)
        directory = (candidate if candidate.is_absolute() else self.execution_root / candidate).resolve()
        if directory != self.execution_root and not directory.is_relative_to(self.execution_root):
            raise ValueError("cwd must stay inside the configured execution workspace")
        if not directory.is_dir():
            raise ValueError("cwd must be an existing directory")
        return directory

    def _run(self, action: Action) -> ActionResult:
        command = self._command(action.arguments.get("command"))
        directory = self._working_directory(action.arguments.get("cwd"))
        timeout = action.arguments.get("timeout_seconds", self.config.execution_timeout_seconds)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
            raise ValueError("timeout_seconds must be an integer between 1 and 300")
        completed = subprocess.run(
            command,
            cwd=directory,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output_limit = 30_000
        details = {
            "command": list(command),
            "cwd": str(directory),
            "return_code": completed.returncode,
            "stdout": completed.stdout[-output_limit:],
            "stderr": completed.stderr[-output_limit:],
            "timed_out": False,
            "executed": True,
        }
        if completed.returncode:
            return ActionResult(action.action_id, False, False, details,
                                f"process exited with code {completed.returncode}")
        return ActionResult(action.action_id, True, False, details)

    def observe(self) -> Observation:
        return Observation(time.time(), "coding-sandbox", dict(self._last_state),
                           {"roots": [str(root) for root in self.roots], "execution": "approval_required",
                            "execution_root": str(self.execution_root), "shell": False})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("coding-sandbox", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "run":
                return self._run(action)
            path = self._path(action.arguments["path"])
            before = self._digest(self._last_state)
            if action.operation == "inspect_file":
                self._remember(path)
                return ActionResult(action.action_id, True, False, {"path": str(path),
                                                                     "content": path.read_text(encoding="utf-8"),
                                                                     "sha256": self._last_state["last_sha256"]})
            if action.operation == "create_file":
                self._snapshot(path)
                path.write_text(str(action.arguments.get("content", "")), encoding="utf-8")
            elif action.operation == "append_text":
                self._snapshot(path)
                path.write_text(path.read_text(encoding="utf-8") + str(action.arguments["text"]), encoding="utf-8")
            elif action.operation == "replace_text":
                self._snapshot(path)
                path.write_text(str(action.arguments["content"]), encoding="utf-8")
            elif action.operation == "rename_file":
                destination = self._path(action.arguments["new_path"])
                self._snapshot(path, destination)
                path.rename(destination)
                path = destination
            elif action.operation == "delete_file":
                self._snapshot(path)
                path.unlink(missing_ok=True)
            else:
                if not self.config.launch_enabled:
                    return ActionResult(action.action_id, False, False, error="Editor launch is disabled")
                subprocess.Popen([str(self.config.editor_executable), str(path)], close_fds=True)
            self._remember(path)
            return ActionResult(action.action_id, True, before != self._digest(self._last_state),
                                {"path": str(path), "state_digest": self._digest(self._last_state), "executed": False})
        except subprocess.TimeoutExpired as error:
            return ActionResult(action.action_id, False, False, {
                "command": list(error.cmd) if isinstance(error.cmd, (list, tuple)) else [str(error.cmd)],
                "stdout": (error.stdout or "")[-30_000:] if isinstance(error.stdout, str) else "",
                "stderr": (error.stderr or "")[-30_000:] if isinstance(error.stderr, str) else "",
                "timed_out": True,
                "executed": True,
            }, f"process timed out after {error.timeout} seconds")
        except (KeyError, OSError, UnicodeError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(observed.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed, "" if matches else "coding post-state differs from expectation")

    def checkpoint(self) -> Checkpoint:
        checkpoint_id = uuid.uuid4().hex
        state = {"roots": [str(root) for root in self.roots]}
        self._checkpoints[checkpoint_id] = {}
        self._active_checkpoint = checkpoint_id
        return Checkpoint(checkpoint_id, state, self._digest(state), time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        snapshots = self._checkpoints.pop(checkpoint.checkpoint_id, None)
        if snapshots is None or self._digest(checkpoint.logical_state) != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self._digest(self._last_state), "checkpoint digest mismatch")
        for value, content in snapshots.items():
            path = Path(value)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        if self._active_checkpoint == checkpoint.checkpoint_id:
            self._active_checkpoint = None
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
