"""Sandboxed Notepad document adapter for lightweight real-program learning tests."""

from __future__ import annotations

import hashlib
import subprocess
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


@dataclass(frozen=True)
class NotepadConfig:
    sandbox_root: Path
    executable: Path = Path(r"C:\Windows\System32\notepad.exe")
    launch_enabled: bool = False
    allowed_roots: tuple[Path, ...] = ()


class NotepadSandboxAdapter(ApplicationInterface):
    """Text-document control surface restricted to configured roots and .txt files."""

    _CAPABILITIES = (
        CapabilityDefinition("inspect_document", False, True, "Read a sandboxed text document."),
        CapabilityDefinition("create_document", True, True, "Create a named sandboxed text document."),
        CapabilityDefinition("append_text", True, False, "Append text to a sandboxed document."),
        CapabilityDefinition("replace_text", True, True, "Replace complete document content."),
        CapabilityDefinition("rename_document", True, True, "Rename a sandboxed text document."),
        CapabilityDefinition("delete_document", True, True, "Delete a sandboxed text document."),
        CapabilityDefinition("open_in_notepad", False, True, "Open a document for human inspection."),
    )

    def __init__(self, config: NotepadConfig):
        self.config = config
        self.root = config.sandbox_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.roots = tuple(dict.fromkeys(root.resolve() for root in config.allowed_roots)) or (self.root,)
        self._open_sandbox = bool(config.allowed_roots)
        self._last_state: dict[str, Any] = {"last_path": None, "last_sha256": None}
        self._open_checkpoints: dict[str, dict[str, bytes | None]] = {}
        self._active_checkpoint: str | None = None
        if not config.executable.is_file():
            raise ValueError(f"Notepad executable not found: {config.executable}")

    def _path(self, name: str) -> Path:
        candidate = Path(name)
        path = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        permitted = any(path.is_relative_to(root) for root in self.roots)
        if not permitted or path.suffix.lower() != ".txt":
            scope = "configured sandbox roots" if self._open_sandbox else "configured sandbox"
            raise ValueError(f"documents must be .txt files inside the {scope}")
        return path

    def _documents(self) -> dict[str, str]:
        if self._open_sandbox:
            return {}
        return {path.name: path.read_text(encoding="utf-8") for path in sorted(self.root.glob("*.txt"))}

    def _snapshot_open_path(self, path: Path) -> None:
        if self._active_checkpoint is None:
            return
        snapshots = self._open_checkpoints[self._active_checkpoint]
        key = str(path)
        if key not in snapshots:
            snapshots[key] = path.read_bytes() if path.exists() else None

    def _record_open_path(self, path: Path) -> None:
        if self._open_sandbox and path.exists():
            self._last_state = {"last_path": str(path), "last_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    @staticmethod
    def _digest(documents: dict[str, str]) -> str:
        encoded = "\n".join(f"{name}\0{content}" for name, content in sorted(documents.items()))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _state_digest(self) -> str:
        return self._digest(self._last_state) if self._open_sandbox else self._digest(self._documents())

    def observe(self) -> Observation:
        documents = self._documents()
        state = self._last_state if self._open_sandbox else {"documents": documents}
        return Observation(time.time(), "windows-notepad", dict(state),
                           {"state_digest": self._digest(documents) if not self._open_sandbox else None,
                            "sandbox": str(self.root), "roots": [str(root) for root in self.roots]})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("windows-notepad", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        before = self._state_digest()
        try:
            name = str(action.arguments.get("name", ""))
            if action.operation == "inspect_document":
                path = self._path(name)
                self._record_open_path(path)
                return ActionResult(action.action_id, True, False, {"content": path.read_text(encoding="utf-8"),
                                                                     "path": str(path)})
            if action.operation == "create_document":
                path = self._path(name); self._snapshot_open_path(path)
                path.write_text(str(action.arguments.get("content", "")), encoding="utf-8")
            elif action.operation == "append_text":
                path = self._path(name); self._snapshot_open_path(path)
                path.write_text(path.read_text(encoding="utf-8") + str(action.arguments["text"]), encoding="utf-8")
            elif action.operation == "replace_text":
                path = self._path(name); self._snapshot_open_path(path)
                path.write_text(str(action.arguments["content"]), encoding="utf-8")
            elif action.operation == "rename_document":
                path = self._path(name); destination = self._path(str(action.arguments["new_name"]))
                self._snapshot_open_path(path); self._snapshot_open_path(destination); path.rename(destination); path = destination
            elif action.operation == "delete_document":
                path = self._path(name); self._snapshot_open_path(path); path.unlink(missing_ok=True)
            else:  # open_in_notepad
                if not self.config.launch_enabled:
                    return ActionResult(action.action_id, False, False, error="Notepad launch is disabled")
                path = self._path(name); subprocess.Popen([str(self.config.executable), str(path)])
            self._record_open_path(path)
            return ActionResult(action.action_id, True, before != self._state_digest(),
                                {"state_digest": self._state_digest(), "path": str(path)})
        except (KeyError, OSError, UnicodeError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(observed.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed,
                                  "" if matches else "Notepad post-state differs from expectation")

    def checkpoint(self) -> Checkpoint:
        if self._open_sandbox:
            checkpoint_id = uuid.uuid4().hex
            self._open_checkpoints[checkpoint_id] = {}
            self._active_checkpoint = checkpoint_id
            state = {"roots": [str(root) for root in self.roots]}
            return Checkpoint(checkpoint_id, state, self._digest(state), time.time())
        documents = deepcopy(self._documents())
        return Checkpoint(uuid.uuid4().hex, {"documents": documents}, self._digest(documents), time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        if self._open_sandbox:
            expected = self._digest(checkpoint.logical_state)
            snapshots = self._open_checkpoints.pop(checkpoint.checkpoint_id, None)
            if expected != checkpoint.digest or snapshots is None:
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
        documents = checkpoint.logical_state.get("documents")
        if not isinstance(documents, dict) or self._digest(documents) != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self._digest(self._documents()), "checkpoint digest mismatch")
        for path in self.root.glob("*.txt"):
            if path.name not in documents:
                path.unlink()
        for name, content in documents.items():
            self._path(name).write_text(content, encoding="utf-8")
        return RollbackResult(True, checkpoint.checkpoint_id, self._digest(self._documents()))
