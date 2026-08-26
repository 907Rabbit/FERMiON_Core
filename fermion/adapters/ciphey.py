"""Local ciphertext decode. User-supplied text only; no network and no file recon."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_CIPHERTEXT_CHARS = 8_000


def _rot13(data: bytes) -> bytes:
    table = bytes.maketrans(
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        b"NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
    )
    return data.translate(table)


def decode_ciphertext(text: str) -> dict[str, Any]:
    """Bounded first-party cascade. Not a claim that the vendored Rust Ciphey ran."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("ciphertext must be non-empty text")
    if len(text) > MAX_CIPHERTEXT_CHARS:
        raise ValueError(f"ciphertext exceeds {MAX_CIPHERTEXT_CHARS} characters")
    raw = text.strip().encode("utf-8")
    candidates: list[dict[str, str]] = []

    def add(name: str, payload: bytes) -> None:
        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError:
            return
        if decoded and decoded != text:
            candidates.append({"decoder": name, "plaintext": decoded[:4_000]})

    padded = raw + b"=" * ((4 - len(raw) % 4) % 4)
    try:
        add("base64", base64.b64decode(padded, validate=False))
    except (binascii.Error, ValueError):
        pass
    try:
        add("hex", bytes.fromhex(text.strip()))
    except ValueError:
        pass
    add("url", unquote_to_bytes(text.strip()))
    add("rot13", _rot13(raw))
    add("reverse", raw[::-1])
    bits = text.strip().replace(" ", "")
    if bits and set(bits) <= {"0", "1"} and len(bits) % 8 == 0:
        add("binary", int(bits, 2).to_bytes(len(bits) // 8, "big"))
    return {
        "backend": "fermion.adapters.ciphey",
        "vendored_ciphey_executed": False,
        "candidate_count": len(candidates),
        "candidates": candidates[:8],
    }


class CipheyAdapter(ApplicationInterface):
    """Decode user-supplied ciphertext. Never launches the vendored Ciphey binary."""

    _CAPABILITIES = (
        CapabilityDefinition("status", False, True, "Report whether the vendored Ciphey tree is present."),
        CapabilityDefinition("decode", False, True, "Decode user-supplied ciphertext locally."),
    )

    def __init__(self, source_root: Path | None = None) -> None:
        self.source_root = (source_root or PROJECT_ROOT).resolve()
        self.tree = self.source_root / "fermion" / "Ciphey"

    def observe(self) -> Observation:
        return Observation(time.time(), "ciphey", {
            "tree_present": self.tree.is_dir(),
            "live_binary_execution": False,
            "network": False,
        })

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("ciphey", self._CAPABILITIES)

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "status":
                return ActionResult(action.action_id, True, False, self.observe().state)
            result = decode_ciphertext(str(action.arguments.get("ciphertext", "")))
            return ActionResult(action.action_id, True, False, result)
        except (KeyError, TypeError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if result.details.get("vendored_ciphey_executed") or result.details.get("live_binary_execution"):
            return VerificationResult(False, expected_effect, observed, "vendored Ciphey binary must not run")
        return VerificationResult(True, expected_effect, observed)

    def checkpoint(self) -> Checkpoint:
        state = self.observe().state
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
