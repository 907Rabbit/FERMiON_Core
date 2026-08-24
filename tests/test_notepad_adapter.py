from __future__ import annotations

import pytest

from fermion.adapters.notepad import NotepadConfig, NotepadSandboxAdapter
from fermion.adapters.notepad_curriculum import NotepadSafeLearningCatalog
from fermion.software.application import Action


def adapter(tmp_path):
    return NotepadSandboxAdapter(NotepadConfig(tmp_path / "FERMiON_Sandbox"))


def test_notepad_adapter_observes_only_sandboxed_documents(tmp_path):
    item = adapter(tmp_path)
    observation = item.observe()
    assert observation.timestamp > 0 and observation.application == "windows-notepad"
    assert observation.state == {"documents": {}}


def test_notepad_adapter_rejects_path_escape(tmp_path):
    item = adapter(tmp_path)
    result = item.execute(Action("create_document", {"name": "../outside.txt", "content": "no"}))
    assert not result.success and "configured sandbox" in result.error


def test_open_sandbox_allows_nested_documents_only_under_configured_roots(tmp_path):
    allowed = tmp_path / "allowed"
    nested = allowed / "nested"
    nested.mkdir(parents=True)
    item = NotepadSandboxAdapter(NotepadConfig(tmp_path / "FERMiON_Sandbox", allowed_roots=(allowed,)))
    document = nested / "note.txt"
    created = item.execute(Action("create_document", {"name": str(document), "content": "open"}))
    assert created.success and document.read_text(encoding="utf-8") == "open"
    assert item.execute(Action("create_document", {"name": str(tmp_path / "outside.txt"), "content": "no"})).success is False


def test_open_sandbox_checkpoint_restores_only_touched_documents(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    document = allowed / "note.txt"
    document.write_text("before", encoding="utf-8")
    item = NotepadSandboxAdapter(NotepadConfig(tmp_path / "FERMiON_Sandbox", allowed_roots=(allowed,)))
    checkpoint = item.checkpoint()
    assert item.execute(Action("replace_text", {"name": str(document), "content": "after"})).success
    assert item.rollback(checkpoint).success
    assert document.read_text(encoding="utf-8") == "before"


def test_document_mutations_verify_and_exactly_rollback(tmp_path):
    item = adapter(tmp_path); checkpoint = item.checkpoint()
    result = item.execute(Action("create_document", {"name": "note.txt", "content": "hello"}))
    assert result.success and item.verify(result, {"documents": {"note.txt": "hello"}}).success
    restored = item.rollback(checkpoint)
    assert restored.success and item.observe().state == {"documents": {}}


def test_catalog_declares_bounded_reversible_experiments():
    catalog = NotepadSafeLearningCatalog()
    assert all(item.rollback_strategy == "checkpoint restore" and item.maximum_action_count == 1
               and item.risk_cost <= 0.1 for item in catalog.templates)


def test_notepad_launch_is_explicitly_disabled_by_default(tmp_path):
    result = adapter(tmp_path).execute(Action("open_in_notepad", {"name": "note.txt"}))
    assert not result.success and result.error == "Notepad launch is disabled"
