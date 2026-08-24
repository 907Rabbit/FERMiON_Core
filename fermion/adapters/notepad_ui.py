"""Optional UI backend for Notepad, verified against the sandbox document oracle.

Desktop automation is deliberately opt-in: tests use a controller seam and the
real controller requires the optional ``pywinauto`` dependency.
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)
from fermion.software.ownership import TargetAssessment, TargetOwnership


class NotepadUIController(Protocol):
    def observe(self) -> dict[str, Any]: ...
    def perform(self, action: Action) -> ActionResult: ...


class PywinautoNotepadController:
    """Accessibility-first controller that validates sandbox, process, window, and edit control."""

    def __init__(self, sandbox_root: str | Path, executable: str | Path = r"C:\Windows\System32\notepad.exe"):
        try:
            from pywinauto import Desktop  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("install pywinauto to enable Notepad UI automation") from error
        self.desktop, self.root, self.executable = Desktop(backend="uia"), Path(sandbox_root).resolve(), Path(executable).resolve()
        if not self.root.is_dir() or not self.executable.is_file():
            raise ValueError("Notepad UI controller requires an existing sandbox and notepad.exe")
        self.expected_pid: int | None = None
        self.expected_path: Path | None = None
        self._ownership = TargetAssessment(TargetOwnership.UNKNOWN, None, "no target acquired")

    def _path(self, value: str) -> Path:
        path = Path(value).resolve()
        if path.parent != self.root or path.suffix.lower() != ".txt":
            raise ValueError("Notepad UI document must be a direct .txt file inside the configured sandbox")
        return path

    @staticmethod
    def _process_image(pid: int) -> Path:
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle: raise RuntimeError("target_process_not_found")
        try:
            size = ctypes.c_ulong(32768); buffer = ctypes.create_unicode_buffer(size.value)
            if not ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                raise RuntimeError("target_process_identity_unavailable")
            return Path(buffer.value).resolve()
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    def _target(self, *, require_edit: bool = False):
        if self.expected_pid is None or self.expected_path is None: raise RuntimeError("target_not_open")
        if self._process_image(self.expected_pid).name.lower() != "notepad.exe": raise RuntimeError("target_process_mismatch")
        window = self.desktop.window(process=self.expected_pid)
        if not window.exists(timeout=2) or not window.is_visible() or self.expected_path.name.lower() not in window.window_text().lower():
            raise RuntimeError("target_window_not_found")
        tabs = window.descendants(control_type="TabItem")
        if tabs and (len(tabs) != 1 or self.expected_path.stem.lower() not in tabs[0].window_text().lower()):
            raise RuntimeError("target_window_shared_session")
        if not require_edit: return window
        documents = window.descendants(control_type="Document")
        if len(documents) != 1: raise RuntimeError("target_control_not_found")
        return window, documents[0]

    def _acquire_open_window(self, path: Path) -> None:
        """Resolve Notepad's single-instance handoff once, then pin future actions to its PID."""
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            candidates = []
            for window in self.desktop.windows():
                try:
                    if (window.is_visible() and path.name.lower() in window.window_text().lower()
                            and self._process_image(window.process_id()).name.lower() == "notepad.exe"):
                        candidates.append(window)
                except Exception:
                    continue
            if len(candidates) == 1:
                self.expected_pid, self.expected_path = candidates[0].process_id(), path
                self._target(require_edit=True)
                self._ownership = TargetAssessment(TargetOwnership.EXCLUSIVE, str(path), "isolated Notepad session acquired")
                return
            if len(candidates) > 1:
                raise RuntimeError("target_window_ambiguous")
            time.sleep(0.2)
        raise RuntimeError("target_window_not_found")

    def _require_isolated_notepad_session(self) -> None:
        for window in self.desktop.windows():
            try:
                image = self._process_image(window.process_id()) if window.is_visible() else None
            except Exception:
                continue
            if image is not None and image.name.lower() == "notepad.exe":
                self._ownership = TargetAssessment(TargetOwnership.SHARED_UNAUTHORIZED, None,
                                                    "a visible Notepad session already exists")
                raise RuntimeError("target_window_shared_session")

    def target_assessment(self) -> TargetAssessment:
        return self._ownership

    @staticmethod
    def _failure(action: Action, error: Exception) -> ActionResult:
        reason = str(error) or type(error).__name__
        return ActionResult(action.action_id, False, False, {"reason": reason,
                            "retryable": reason in {"target_window_not_found", "target_control_not_found", "target_not_open",
                                                       "target_window_shared_session"}}, reason)

    def observe(self) -> dict[str, Any]:
        try:
            window = self._target()
            return {"title": window.window_text(), "visible": bool(window.is_visible()), "enabled": bool(window.is_enabled()),
                    "process_id": self.expected_pid, "document": str(self.expected_path), "backend": "accessibility"}
        except Exception as error:
            return {"error": str(error), "backend": "accessibility"}

    def perform(self, action: Action) -> ActionResult:
        try:
            if action.operation == "open_document":
                path = self._path(str(action.arguments["path"]))
                if not path.exists(): raise RuntimeError("sandbox_document_not_found")
                self._require_isolated_notepad_session()
                subprocess.Popen([str(self.executable), str(path)])
                self._acquire_open_window(path)
            elif action.operation == "move_cursor_end":
                _, document = self._target(require_edit=True); document.type_keys("^{END}")
            elif action.operation == "type_text":
                _, document = self._target(require_edit=True)
                text = str(action.arguments["text"]).replace("\r\n", "\n").replace("\n", "{ENTER}")
                document.set_focus(); document.type_keys(text, with_spaces=True)
            elif action.operation == "select_all":
                _, document = self._target(require_edit=True); document.type_keys("^a")
            # Modern Windows Notepad exposes a Document control but not the legacy
            # menu wrapper. These are declared, target-bound shortcuts—not a
            # fallback: ownership, window, and Document control are revalidated.
            elif action.operation == "save_document":
                _, document = self._target(require_edit=True); document.type_keys("^s")
            elif action.operation == "undo":
                _, document = self._target(require_edit=True); document.type_keys("^z")
            elif action.operation == "close_without_saving":
                window, _ = self._target(require_edit=True)
                buttons = [item for item in window.descendants(control_type="Button")
                           if item.element_info.automation_id == "CloseButton"]
                if len(buttons) != 1: raise RuntimeError("target_close_control_not_found")
                buttons[0].click_input()
            else: return ActionResult(action.action_id, False, False, error="unsupported Notepad UI action")
            return ActionResult(action.action_id, True, True, {"ui": self.observe()})
        except Exception as error:
            return self._failure(action, error)


class NotepadUIAdapter(ApplicationInterface):
    """UI-only observation/action surface; document truth comes from the oracle adapter."""

    _CAPABILITIES = (
        CapabilityDefinition("open_document", False, True, "Open a sandbox document through Notepad UI."),
        CapabilityDefinition("move_cursor_end", False, True, "Move the document cursor to its end."),
        CapabilityDefinition("type_text", True, False, "Type text into the active editor."),
        CapabilityDefinition("save_document", False, True, "Save the active document."),
        CapabilityDefinition("select_all", False, True, "Select all editor text."),
        CapabilityDefinition("undo", True, True, "Undo most recent editor change."),
        CapabilityDefinition("close_without_saving", True, True, "Close active editor without saving."),
    )

    def __init__(self, controller: NotepadUIController):
        self.controller = controller

    def observe(self) -> Observation:
        return Observation(__import__("time").time(), "windows-notepad-ui", self.controller.observe(),
                           {"observation_priority": "accessibility"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("windows-notepad-ui", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        return self.controller.perform(action)

    def target_assessment(self) -> TargetAssessment:
        getter = getattr(self.controller, "target_assessment", None)
        return getter() if callable(getter) else TargetAssessment(TargetOwnership.UNKNOWN, None, "UI controller has no ownership proof")

    def is_mutating(self, action: Action) -> bool:
        return action.operation in {"type_text", "undo", "close_without_saving"}

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        return VerificationResult(result.success, expected_effect, observed, result.error or "")

    def checkpoint(self) -> Checkpoint:
        raise RuntimeError("UI-only Notepad adapter has no reliable checkpoint; use the document oracle")

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        return RollbackResult(False, checkpoint.checkpoint_id, "", "UI-only rollback is not authoritative")


@dataclass(frozen=True)
class UIOracleComparison:
    ui_reported_success: bool
    oracle_verified: bool
    disagreement: bool
    reason: str


class ClosedLoopNotepadAdapter(ApplicationInterface):
    """Routes actions to Notepad UI and verifies durable effects with document truth."""

    def __init__(self, ui: NotepadUIAdapter, oracle: ApplicationInterface):
        self.ui, self.oracle = ui, oracle

    def observe(self) -> Observation:
        ui_state, oracle_state = self.ui.observe(), self.oracle.observe()
        return Observation(ui_state.timestamp, "windows-notepad-closed-loop",
                           {"ui": ui_state.state, "document": oracle_state.state},
                           {"ui_priority": "accessibility", "document_oracle": True})

    def capabilities(self) -> CapabilitySet:
        return self.ui.capabilities()

    def execute(self, action: Action) -> ActionResult:
        return self.ui.execute(action)

    def target_assessment(self) -> TargetAssessment:
        return self.ui.target_assessment()

    def is_mutating(self, action: Action) -> bool:
        return self.ui.is_mutating(action)

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        oracle = self.oracle.verify(result, expected_effect)
        comparison = UIOracleComparison(result.success, oracle.success, result.success != oracle.success,
                                        oracle.reason if result.success else result.error or "UI action failed")
        return VerificationResult(oracle.success, expected_effect,
                                  {"oracle": oracle.observed_effect, "comparison": comparison.__dict__}, comparison.reason)

    def checkpoint(self) -> Checkpoint:
        return self.oracle.checkpoint()

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        return self.oracle.rollback(checkpoint)


@dataclass(frozen=True)
class ProgramLearningMetrics:
    task_success: int
    experiments_to_promotion: int
    failed_actions: int
    false_failure_signals: int
    rollbacks: int
    primitive_actions: int
    transfer_success: int
    recovery_success: int
    oracle_disagreements: int = 0
    approval_requests: int = 0
    skill_reuse: int = 0
    experiments_to_first_success: int = 0


def compare_gse_ablation(gse: ProgramLearningMetrics, baseline: ProgramLearningMetrics) -> dict[str, tuple[int, int]]:
    """Produces a frozen, comparable metric row; interpretation remains empirical."""
    return {field: (getattr(gse, field), getattr(baseline, field)) for field in ProgramLearningMetrics.__dataclass_fields__}
