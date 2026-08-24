"""Optional Windows accessibility and screenshot observation providers."""

from __future__ import annotations

import hashlib
import io
from typing import Any


class OptionalDependencyError(RuntimeError):
    pass


class WindowsAccessibilityProvider:
    name = "accessibility"

    def __init__(self, title_re: str = ".*", maximum_controls: int = 500):
        self.title_re = title_re
        self.maximum_controls = maximum_controls

    def observe(self) -> list[dict[str, Any]]:
        try:
            from pywinauto import Desktop  # type: ignore[import-not-found]
        except ImportError as error:
            raise OptionalDependencyError("install pywinauto to observe Windows UI Automation") from error
        controls = []
        for window in Desktop(backend="uia").windows(title_re=self.title_re, visible_only=True):
            for control in window.descendants()[:self.maximum_controls]:
                info = control.element_info
                rectangle = info.rectangle
                controls.append({"name": info.name, "control_type": info.control_type,
                                 "automation_id": info.automation_id,
                                 "rectangle": [rectangle.left, rectangle.top,
                                               rectangle.right, rectangle.bottom],
                                 "enabled": control.is_enabled(), "visible": control.is_visible()})
        return controls


class ScreenshotProvider:
    name = "vision"

    def observe(self) -> dict[str, Any]:
        try:
            from PIL import ImageGrab  # type: ignore[import-not-found]
        except ImportError as error:
            raise OptionalDependencyError("install Pillow to capture screenshots") from error
        image = ImageGrab.grab(all_screens=True)
        stream = io.BytesIO(); image.save(stream, format="PNG")
        data = stream.getvalue()
        return {"width": image.width, "height": image.height, "mode": image.mode,
                "sha256": hashlib.sha256(data).hexdigest()}
