"""Observation bus and auditable filesystem provider."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ObservationSnapshot:
    timestamp: float
    channels: dict[str, Any]
    provider_errors: dict[str, str] = field(default_factory=dict)


class ObservationProvider(Protocol):
    name: str

    def observe(self) -> Any: ...


def file_manifest(root: Path, ignored: tuple[str, ...] = (".git", ".venv", "__pycache__")) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.relative_to(root).parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[path.relative_to(root).as_posix()] = digest
    return manifest


class FileSystemProvider:
    name = "filesystem"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def observe(self) -> dict[str, str]:
        return file_manifest(self.root)


class ObservationBus:
    def __init__(self, providers: list[ObservationProvider] | None = None):
        self.providers = list(providers or [])

    def register(self, provider: ObservationProvider) -> None:
        self.providers.append(provider)

    def observe(self) -> ObservationSnapshot:
        channels, errors = {}, {}
        for provider in self.providers:
            try:
                channels[provider.name] = provider.observe()
            except Exception as error:  # A failed sensor is recorded, not treated as absent evidence.
                errors[provider.name] = f"{type(error).__name__}: {error}"
        return ObservationSnapshot(time.time(), channels, errors)

