"""Local-only GGUF discovery.  This module never downloads models."""
from __future__ import annotations

import os
from pathlib import Path


def default_model_directories(project_root: str | Path = ".") -> list[Path]:
    user = Path(os.environ.get("USERPROFILE", Path.home()))
    roots = [Path("G:/models"), Path("G:/Models"), Path("G:/AI/models"), Path("D:/models"),
             Path("C:/models"), user / "models", Path(project_root) / "models"]
    return [root for root in roots if root.is_dir()]


def discover_models(directories: list[str | Path] | None = None, project_root: str | Path = ".") -> list[Path]:
    """Return unique GGUF files in configured local directories, sorted by path."""
    roots = [Path(item).expanduser() for item in (directories or default_model_directories(project_root))]
    found: dict[str, Path] = {}
    for root in roots:
        if root.is_dir():
            for model in root.rglob("*.gguf"):
                if model.is_file():
                    found[str(model.resolve()).lower()] = model.resolve()
    return sorted(found.values(), key=lambda item: str(item).lower())
