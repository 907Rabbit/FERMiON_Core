"""Typed, non-executing source-file control for the FERMiON coding sandbox."""

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


class CodingSandboxAdapter(ApplicationInterface):
    """Edit approved text/source files; never execute, compile, or shell out to code."""

    _CAPABILITIES = (
        CapabilityDefinition("inspect_file", False, True, "Read a source or text file."),
        CapabilityDefinition("create_file", True, True, "Create a source or text file."),
        CapabilityDefinition("append_text", True, False, "Append text to a source or text file."),
        CapabilityDefinition("replace_text", True, True, "Replace complete source or text file content."),
        CapabilityDefinition("rename_file", True, True, "Rename a source or text file."),
        CapabilityDefinition("delete_file", True, True, "Delete a source or text file."),
        CapabilityDefinition("open_in_editor", False, True, "Open a file in the configured editor; never run it."),
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

    def observe(self) -> Observation:
        return Observation(time.time(), "coding-sandbox", dict(self._last_state),
                           {"roots": [str(root) for root in self.roots], "execution": "disabled"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("coding-sandbox", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
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
