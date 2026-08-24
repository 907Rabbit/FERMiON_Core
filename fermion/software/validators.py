"""Deterministic validators; model opinion is never authoritative evidence."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fermion.hr.contracts import ValidatorEvidence


@dataclass(frozen=True)
class ValidationContext:
    workspace: Path
    return_code: int | None
    stdout: str
    stderr: str
    changed_artifacts: tuple[str, ...]
    undeclared_artifacts: tuple[str, ...]
    timed_out: bool


class Validator(Protocol):
    name: str

    def validate(self, context: ValidationContext) -> ValidatorEvidence: ...


class ExitCodeValidator:
    name = "exit_code"

    def validate(self, context: ValidationContext) -> ValidatorEvidence:
        observed = context.return_code is not None and not context.timed_out
        success = observed and context.return_code == 0
        return ValidatorEvidence(float(success), float(observed), float(success),
                                 float(bool(context.undeclared_artifacts)),
                                 {"return_code": context.return_code, "timed_out": context.timed_out})


class FileExistsValidator:
    name = "file_exists"

    def __init__(self, relative_path: str, *, nonempty: bool = True):
        self.relative_path = relative_path
        self.nonempty = nonempty

    def validate(self, context: ValidationContext) -> ValidatorEvidence:
        path = _safe_path(context.workspace, self.relative_path)
        exists = path.is_file()
        success = exists and (not self.nonempty or path.stat().st_size > 0)
        return ValidatorEvidence(float(success), 1.0, float(success),
                                 float(bool(context.undeclared_artifacts)),
                                 {"path": self.relative_path, "exists": exists})


class JSONValidator:
    name = "json"

    def __init__(self, relative_path: str, required_keys: tuple[str, ...] = (),
                 expected: dict[str, Any] | None = None, tolerance: float = 1e-8):
        self.relative_path = relative_path
        self.required_keys = required_keys
        self.expected = expected or {}
        self.tolerance = tolerance

    def validate(self, context: ValidationContext) -> ValidatorEvidence:
        path = _safe_path(context.workspace, self.relative_path)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            keys_ok = isinstance(value, dict) and all(key in value for key in self.required_keys)
            values_ok = keys_ok and all(_equal(value.get(key), expected, self.tolerance)
                                        for key, expected in self.expected.items())
            success, details = keys_ok and values_ok, {"keys": sorted(value) if isinstance(value, dict) else []}
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            success, details = False, {"error": f"{type(error).__name__}: {error}"}
        return ValidatorEvidence(float(success), 1.0, float(success),
                                 float(bool(context.undeclared_artifacts)), details)


class CompositeValidator:
    name = "composite"

    def __init__(self, validators: list[Validator], require_all: bool = True):
        if not validators:
            raise ValueError("a composite validator requires children")
        self.validators = validators
        self.require_all = require_all

    def validate(self, context: ValidationContext) -> ValidatorEvidence:
        evidence = [validator.validate(context) for validator in self.validators]
        successes = [item.success >= 0.5 for item in evidence]
        success = all(successes) if self.require_all else any(successes)
        return ValidatorEvidence(float(success), min(item.information for item in evidence),
                                 sum(item.goal_score for item in evidence) / len(evidence),
                                 max(item.contradiction for item in evidence),
                                 {validator.name: item.details for validator, item in zip(self.validators, evidence)})


def _safe_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"validator path escapes workspace: {relative_path}") from error
    return path


def _equal(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    return actual == expected

