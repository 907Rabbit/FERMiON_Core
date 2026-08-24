from __future__ import annotations

import hashlib

from fermion.adapters.imhex import ImHexReadOnlyAdapter
from fermion.software.application import Action


def test_imhex_read_only_adapter_inspects_reads_and_searches(tmp_path):
    target = tmp_path / "sample.bin"
    target.write_bytes(b"AB\x00AB\xff")
    adapter = ImHexReadOnlyAdapter((tmp_path,))

    inspected = adapter.execute(Action("inspect_file", {"path": str(target)}))
    assert inspected.success
    assert inspected.details["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()

    read = adapter.execute(Action("read_bytes", {"path": str(target), "offset": 2, "length": 3}))
    assert read.success and read.details["hex"] == "004142"

    found = adapter.execute(Action("search_hex", {"path": str(target), "pattern_hex": "4142"}))
    assert found.success and found.details["offsets"] == [0, 3]


def test_imhex_read_only_adapter_rejects_outside_roots(tmp_path):
    inside = tmp_path / "inside"
    inside.mkdir()
    target = tmp_path / "outside.bin"
    target.write_bytes(b"x")
    adapter = ImHexReadOnlyAdapter((inside,))
    assert not adapter.execute(Action("inspect_file", {"path": str(target)})).success
