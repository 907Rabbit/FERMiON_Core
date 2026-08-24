"""Generic, catalog-backed local Windows program adapter.

Programs are registered by a user-visible alias and launched as an argv vector,
never through a shell.  FERMiON can inspect and close only processes it started.
"""

from __future__ import annotations

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
class ProgramEntry:
    alias: str
    executable: str
    description: str = ""


class LocalProgramAdapter(ApplicationInterface):
    """An extensible, direct-executable control surface for local programs."""

    _CAPABILITIES = (
        CapabilityDefinition("list_programs", False, True, "List registered local program aliases."),
        CapabilityDefinition("register_program", True, True, "Register a trusted executable under an alias."),
        CapabilityDefinition("launch_program", True, False, "Launch a registered program with literal arguments."),
        CapabilityDefinition("inspect_program", False, True, "Inspect a FERMiON-launched process."),
        CapabilityDefinition("close_program", True, True, "Close a FERMiON-launched process."),
    )
    _DENIED_EXECUTABLES = {"cmd.exe", "powershell.exe", "pwsh.exe", "python.exe", "pythonw.exe", "wscript.exe", "cscript.exe"}

    def __init__(self, catalog_path: Path, trusted_roots: tuple[Path, ...], entries: tuple[ProgramEntry, ...] = ()) -> None:
        self.catalog_path = catalog_path
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.trusted_roots = tuple(root.resolve() for root in trusted_roots if root.exists())
        self._entries: dict[str, ProgramEntry] = {}
        self._processes: dict[int, subprocess.Popen[str]] = {}
        if self.catalog_path.exists():
            for item in json.loads(self.catalog_path.read_text(encoding="utf-8")):
                entry = ProgramEntry(**item)
                self._entries[entry.alias] = entry
        for entry in entries:
            if entry.alias not in self._entries and self._valid_executable(Path(entry.executable)):
                self._entries[entry.alias] = entry
        self._save()

    def _save(self) -> None:
        self.catalog_path.write_text(json.dumps([entry.__dict__ for entry in self._entries.values()], indent=2,
                                                sort_keys=True), encoding="utf-8")

    def _valid_executable(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            if not resolved.is_file() or resolved.suffix.lower() != ".exe" or resolved.name.lower() in self._DENIED_EXECUTABLES:
                return False
            return any(resolved.is_relative_to(root) for root in self.trusted_roots)
        except OSError:
            return False

    def _entry(self, alias: str) -> ProgramEntry:
        entry = self._entries.get(alias)
        if entry is None:
            raise ValueError(f"unknown registered program: {alias}")
        if not self._valid_executable(Path(entry.executable)):
            raise ValueError(f"registered program is unavailable or outside trusted roots: {alias}")
        return entry

    def _state(self) -> dict[str, Any]:
        launched = []
        for pid, process in list(self._processes.items()):
            if process.poll() is not None:
                self._processes.pop(pid)
                continue
            launched.append({"process_id": pid, "alias": next((entry.alias for entry in self._entries.values()
                                                                    if entry.executable == str(process.args[0])), "unknown")})
        return {"registered_programs": [entry.__dict__ for entry in self._entries.values()], "launched": launched}

    def observe(self) -> Observation:
        return Observation(time.time(), "local-programs", self._state(), {"interface": "direct-executable"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("local-programs", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "list_programs":
                return ActionResult(action.action_id, True, False, {"programs": self._state()["registered_programs"]})
            if action.operation == "register_program":
                alias = str(action.arguments["alias"]).strip().lower()
                if not alias.replace("_", "").replace("-", "").isalnum():
                    raise ValueError("program alias may contain only letters, digits, hyphens, and underscores")
                executable = Path(str(action.arguments["executable"])).resolve()
                if not self._valid_executable(executable):
                    raise ValueError("executable is not a trusted local .exe")
                self._entries[alias] = ProgramEntry(alias, str(executable), str(action.arguments.get("description", "")))
                self._save()
                return ActionResult(action.action_id, True, True, {"program": self._entries[alias].__dict__})
            if action.operation == "launch_program":
                entry = self._entry(str(action.arguments["alias"]))
                arguments = action.arguments.get("arguments", [])
                if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
                    raise ValueError("program arguments must be a list of strings")
                if len(arguments) > 24 or sum(len(item) for item in arguments) > 4096:
                    raise ValueError("program arguments exceed the local-program limit")
                process = subprocess.Popen([entry.executable, *arguments], close_fds=True)
                self._processes[process.pid] = process
                return ActionResult(action.action_id, True, True, {"process_id": process.pid, "alias": entry.alias})
            pid = int(action.arguments["process_id"])
            process = self._processes.get(pid)
            if process is None:
                raise ValueError("process was not launched by FERMiON")
            if action.operation == "inspect_program":
                return ActionResult(action.action_id, True, False, {"process_id": pid, "running": process.poll() is None,
                                                                      "return_code": process.poll()})
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            self._processes.pop(pid, None)
            return ActionResult(action.action_id, True, True, {"process_id": pid, "closed": True})
        except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        state = self._state()
        digest = __import__("hashlib").sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        prior = {item["process_id"] for item in checkpoint.logical_state.get("launched", [])}
        for pid, process in list(self._processes.items()):
            if pid not in prior and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                self._processes.pop(pid, None)
        digest = __import__("hashlib").sha256(json.dumps(self._state(), sort_keys=True).encode("utf-8")).hexdigest()
        return RollbackResult(True, checkpoint.checkpoint_id, digest)


def discovered_local_programs() -> tuple[ProgramEntry, ...]:
    """Small default catalog; users can register more trusted applications at runtime."""
    candidates = (
        ProgramEntry("lm_studio", r"F:\LM Studio\LM Studio.exe", "Local model workstation."),
        ProgramEntry("ollama", r"F:\Ollama\ollama app.exe", "Local Ollama desktop application."),
    )
    return tuple(item for item in candidates if Path(item.executable).is_file())
