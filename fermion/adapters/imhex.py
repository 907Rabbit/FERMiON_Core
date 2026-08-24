"""Read-only binary inspection surface for ImHex workflows.

This adapter deliberately does not patch, save, or otherwise modify target
files.  Launching ImHex itself remains available through ``local_programs``;
the adapter supplies bounded, auditable observations that a generic planner can
use before a user opens a file in the GUI.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


class ImHexReadOnlyAdapter(ApplicationInterface):
    """Inspect approved binary roots without exposing mutation operations."""

    _CAPABILITIES = (
        CapabilityDefinition("inspect_file", False, True, "Return size, timestamps, and SHA-256 for a binary file."),
        CapabilityDefinition("read_bytes", False, True, "Read a bounded range of bytes as hexadecimal."),
        CapabilityDefinition("search_hex", False, True, "Find a bounded number of hexadecimal byte-pattern matches."),
    )
    _MAX_READ = 65_536
    _MAX_FILE_SIZE = 512 * 1024 * 1024
    _MAX_RESULTS = 100

    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.roots = tuple(root.resolve() for root in roots if root.exists())
        self._last_observation: dict[str, Any] = {"last_path": None, "last_sha256": None}

    def _resolve(self, value: Any) -> Path:
        path = Path(str(value)).resolve()
        if not path.is_file() or not any(path.is_relative_to(root) for root in self.roots):
            raise ValueError("file is unavailable or outside ImHex inspection roots")
        if path.stat().st_size > self._MAX_FILE_SIZE:
            raise ValueError("file exceeds the 512 MiB inspection limit")
        return path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1_048_576), b""):
                digest.update(block)
        return digest.hexdigest()

    def _metadata(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        digest = self._sha256(path)
        self._last_observation = {"last_path": str(path), "last_sha256": digest}
        return {"path": str(path), "size": stat.st_size, "modified": stat.st_mtime, "sha256": digest}

    def observe(self) -> Observation:
        return Observation(time.time(), "imhex", dict(self._last_observation), {"interface": "read-only-filesystem"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("imhex", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            path = self._resolve(action.arguments["path"])
            if action.operation == "inspect_file":
                return ActionResult(action.action_id, True, False, self._metadata(path))
            if action.operation == "read_bytes":
                offset = int(action.arguments.get("offset", 0))
                length = int(action.arguments.get("length", 256))
                if offset < 0 or length < 1 or length > self._MAX_READ:
                    raise ValueError("offset must be non-negative and length must be 1..65536")
                with path.open("rb") as stream:
                    stream.seek(offset)
                    data = stream.read(length)
                return ActionResult(action.action_id, True, False,
                                    {**self._metadata(path), "offset": offset, "length": len(data), "hex": data.hex()})
            pattern = str(action.arguments["pattern_hex"]).replace(" ", "")
            needle = bytes.fromhex(pattern)
            if not needle:
                raise ValueError("pattern_hex must contain at least one byte")
            requested = int(action.arguments.get("max_results", 20))
            if requested < 1 or requested > self._MAX_RESULTS:
                raise ValueError("max_results must be 1..100")
            data = path.read_bytes()
            matches: list[int] = []
            start = 0
            while len(matches) < requested:
                found = data.find(needle, start)
                if found < 0:
                    break
                matches.append(found)
                start = found + 1
            return ActionResult(action.action_id, True, False,
                                {**self._metadata(path), "pattern_hex": needle.hex(), "offsets": matches})
        except (KeyError, OSError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(result.details.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed, "" if matches else "inspection result differs from expectation")

    def checkpoint(self) -> Checkpoint:
        state = dict(self._last_observation)
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        expected = hashlib.sha256(json.dumps(checkpoint.logical_state, sort_keys=True).encode("utf-8")).hexdigest()
        if expected != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self.checkpoint().digest, "checkpoint digest mismatch")
        self._last_observation = dict(checkpoint.logical_state)
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
