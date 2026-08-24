"""Interface preference: native API, accessibility, then visual GUI control."""

from __future__ import annotations

from enum import IntEnum

from .capabilities import Capability


class InterfacePriority(IntEnum):
    NATIVE_API = 0
    ACCESSIBILITY = 1
    VISION_GUI = 2


def rank_capabilities(capabilities: list[Capability]) -> list[Capability]:
    priorities = {"api": InterfacePriority.NATIVE_API, "cli": InterfacePriority.NATIVE_API,
                  "accessibility": InterfacePriority.ACCESSIBILITY,
                  "gui": InterfacePriority.VISION_GUI, "vision": InterfacePriority.VISION_GUI}
    return sorted(capabilities, key=lambda item: (
        priorities.get(item.interface.lower(), InterfacePriority.VISION_GUI), -item.reliability))

