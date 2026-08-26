"""Bounded, auditable pytest execution with durable local receipts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from .integration_registry import sha256_bytes


SCHEMA_VERSION = "fermion-test-receipt-v1"


@dataclass(frozen=True)
class TestReceipt:
    schema_version: str
    command: tuple[str, ...]
    working_directory: str
    started_at_utc: str
    completed_at_utc: str
    elapsed_seconds: float
    exit_code: int
    stdout_path: str
    stdout_sha256: str
    stderr_path: str
    stderr_sha256: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "succeeded": self.succeeded}

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "TestReceipt":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        payload = {key: value[key] for key in allowed}
        payload["command"] = tuple(payload["command"])
        return cls(**payload)  # type: ignore[arg-type]


def run_pytest_with_receipt(
    *, root: Path, receipt_path: Path, pytest_args: Sequence[str]
) -> TestReceipt:
    """Run pytest only, requiring an isolated basetemp and recording its exact result."""
    if not pytest_args:
        raise ValueError("pytest arguments are required")
    base_temp = _basetemp_path(pytest_args)
    if base_temp is None:
        raise ValueError("an explicit --basetemp is required for an isolated test receipt")

    root = root.resolve()
    receipt_path = receipt_path.resolve()
    base_temp.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = receipt_path.with_suffix(".stdout.log")
    stderr_path = receipt_path.with_suffix(".stderr.log")
    command = (sys.executable, "-m", "pytest", *pytest_args)
    started = datetime.now(UTC)
    completed = started
    result: subprocess.CompletedProcess[bytes] | None = None
    try:
        result = subprocess.run(command, cwd=root, check=False, capture_output=True)
        completed = datetime.now(UTC)
        stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
    finally:
        if result is None:
            completed = datetime.now(UTC)
            stdout, stderr, exit_code = b"", b"pytest did not start", 125
        _atomic_write_bytes(stdout_path, stdout)
        _atomic_write_bytes(stderr_path, stderr)

    receipt = TestReceipt(
        schema_version=SCHEMA_VERSION,
        command=command,
        working_directory=str(root),
        started_at_utc=started.isoformat(),
        completed_at_utc=completed.isoformat(),
        elapsed_seconds=round((completed - started).total_seconds(), 6),
        exit_code=exit_code,
        stdout_path=str(stdout_path),
        stdout_sha256=sha256_bytes(stdout),
        stderr_path=str(stderr_path),
        stderr_sha256=sha256_bytes(stderr),
    )
    _atomic_write_text(receipt_path, json.dumps(receipt.to_dict(), indent=2) + "\n")
    return receipt


def verify_test_receipt(receipt_path: Path) -> TestReceipt:
    """Verify a completed receipt and its immutable log contents without rerunning tests."""
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt = TestReceipt.from_dict(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid test receipt") from error
    if receipt.schema_version != SCHEMA_VERSION:
        raise ValueError("unsupported test receipt schema")
    if payload.get("succeeded") != receipt.succeeded:
        raise ValueError("test receipt success flag does not match exit code")
    for path_text, expected_hash in ((receipt.stdout_path, receipt.stdout_sha256),
                                     (receipt.stderr_path, receipt.stderr_sha256)):
        path = Path(path_text)
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected_hash:
            raise ValueError(f"test receipt log integrity failure: {path}")
    return receipt


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _basetemp_path(pytest_args: Sequence[str]) -> Path | None:
    for index, value in enumerate(pytest_args):
        if value == "--basetemp" and index + 1 < len(pytest_args):
            return Path(pytest_args[index + 1]).resolve()
        if value.startswith("--basetemp="):
            return Path(value.split("=", 1)[1]).resolve()
    return None
