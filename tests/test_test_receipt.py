from __future__ import annotations

import json
from pathlib import Path

import pytest

from fermion.cognitive.test_receipt import run_pytest_with_receipt, verify_test_receipt
from fermion.cognitive.integration_registry import sha256_bytes


def test_receipt_records_a_passing_pytest_run(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_passes():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"

    receipt = run_pytest_with_receipt(
        root=tmp_path,
        receipt_path=receipt_path,
        pytest_args=("-q", "--basetemp", str(tmp_path / "nested" / "base"), str(test_file)),
    )

    stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt.succeeded
    assert stored["exit_code"] == 0
    assert stored["stdout_sha256"] == sha256_bytes(Path(stored["stdout_path"]).read_bytes())
    assert "1 passed" in Path(stored["stdout_path"]).read_text(encoding="utf-8")
    assert verify_test_receipt(receipt_path) == receipt


def test_receipt_requires_an_explicit_basetemp(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--basetemp"):
        run_pytest_with_receipt(root=tmp_path, receipt_path=tmp_path / "receipt.json", pytest_args=("-q",))


def test_receipt_verifier_rejects_a_tampered_log(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_passes():\n    assert True\n", encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    receipt = run_pytest_with_receipt(
        root=tmp_path,
        receipt_path=receipt_path,
        pytest_args=("-q", "--basetemp=" + str(tmp_path / "base"), str(test_file)),
    )
    Path(receipt.stdout_path).write_text("altered", encoding="utf-8")

    with pytest.raises(ValueError, match="log integrity"):
        verify_test_receipt(receipt_path)
