"""Opt-in live desktop gate. Run: $env:FERMION_LIVE_UI='1'; pytest -m windows_ui."""

from __future__ import annotations

import os
import uuid
import pytest

from fermion.adapters.notepad import NotepadConfig, NotepadSandboxAdapter
from fermion.adapters.notepad_ui import ClosedLoopNotepadAdapter, NotepadUIAdapter, PywinautoNotepadController
from fermion.software.application import Action

pytestmark = pytest.mark.windows_ui


@pytest.mark.skipif(os.environ.get("FERMION_LIVE_UI") != "1", reason="set FERMION_LIVE_UI=1 on an interactive desktop")
def test_live_notepad_open_append_save_oracle_verify_and_rollback(tmp_path):
    pytest.importorskip("pywinauto")
    oracle = NotepadSandboxAdapter(NotepadConfig(tmp_path / "FERMiON_Sandbox"))
    filename = f"fermion_live_{uuid.uuid4().hex}.txt"
    oracle.execute(Action("create_document", {"name": filename, "content": "Alpha"}))
    adapter = ClosedLoopNotepadAdapter(NotepadUIAdapter(PywinautoNotepadController(oracle.root)), oracle)
    checkpoint = adapter.checkpoint()
    opened = adapter.execute(Action("open_document", {"path": str(oracle.root / filename)}))
    if opened.error == "target_window_shared_session":
        pytest.skip("close existing Notepad tabs before running the isolated live UI gate")
    assert opened.success
    try:
        assert adapter.execute(Action("move_cursor_end")).success
        typed = adapter.execute(Action("type_text", {"text": "\nBeta"}))
        assert typed.success and adapter.execute(Action("save_document")).success
        assert adapter.verify(typed, {"documents": {filename: "Alpha\nBeta"}}).success
    finally:
        adapter.execute(Action("close_without_saving"))
        assert adapter.rollback(checkpoint).success
