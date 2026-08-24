"""Ordered action backends for API, accessibility, and visual GUI fallback."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

from .windows import OptionalDependencyError


@dataclass(frozen=True)
class Action:
    operation: str
    arguments: dict[str, Any]
    interface: str


@dataclass(frozen=True)
class ActionOutcome:
    success: bool
    interface: str
    details: dict[str, Any]


class ActionBackend(Protocol):
    interface: str

    def supports(self, action: Action) -> bool: ...
    def execute(self, action: Action) -> ActionOutcome: ...


class NativeCommandBackend:
    """Runs an explicit argv vector; shell parsing is never enabled."""

    interface = "api"

    def supports(self, action: Action) -> bool:
        return action.interface in {"api", "cli"} and action.operation == "command"

    def execute(self, action: Action) -> ActionOutcome:
        argv = action.arguments.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise ValueError("native command actions require a nonempty string argv list")
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=float(action.arguments.get("timeout", 30)))
        return ActionOutcome(completed.returncode == 0, self.interface,
                             {"return_code": completed.returncode,
                              "stdout": completed.stdout, "stderr": completed.stderr})


class AccessibilityBackend:
    interface = "accessibility"

    def supports(self, action: Action) -> bool:
        return action.interface == self.interface and action.operation in {"click", "type"}

    def execute(self, action: Action) -> ActionOutcome:
        try:
            from pywinauto import Desktop  # type: ignore[import-not-found]
        except ImportError as error:
            raise OptionalDependencyError("install pywinauto for accessibility actions") from error
        window = Desktop(backend="uia").window(title_re=action.arguments.get("window", ".*"))
        control = window.child_window(auto_id=action.arguments.get("automation_id"),
                                      title=action.arguments.get("title"),
                                      control_type=action.arguments.get("control_type"))
        if action.operation == "click":
            control.click_input()
        else:
            control.set_edit_text(str(action.arguments["text"]))
        return ActionOutcome(True, self.interface, {"control": str(control)})


class VisualGUIBackend:
    interface = "gui"

    def supports(self, action: Action) -> bool:
        return action.interface in {"gui", "vision"} and action.operation in {"click", "type", "hotkey"}

    def execute(self, action: Action) -> ActionOutcome:
        try:
            import pyautogui  # type: ignore[import-not-found]
        except ImportError as error:
            raise OptionalDependencyError("install pyautogui for visual GUI actions") from error
        if action.operation == "click":
            pyautogui.click(int(action.arguments["x"]), int(action.arguments["y"]))
        elif action.operation == "type":
            pyautogui.write(str(action.arguments["text"]), interval=0.01)
        else:
            pyautogui.hotkey(*action.arguments["keys"])
        return ActionOutcome(True, self.interface, {})


class ActionDispatcher:
    def __init__(self, backends: list[ActionBackend] | None = None):
        self.backends = backends or [NativeCommandBackend(), AccessibilityBackend(), VisualGUIBackend()]

    def execute(self, action: Action) -> ActionOutcome:
        for backend in self.backends:
            if backend.supports(action):
                return backend.execute(action)
        raise ValueError(f"no action backend supports {action.interface}:{action.operation}")

