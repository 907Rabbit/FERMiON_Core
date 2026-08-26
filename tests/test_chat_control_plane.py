import json
from pathlib import Path

from fermion.cognitive.runtime import CognitiveRuntime, RuntimeConfig
from fermion.control_plane import default_control_plane


def test_chat_validates_a_control_plane_plan_without_executing(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    payload = json.dumps({
        "summary": "Create a sandbox note.",
        "requires_approval": True,
        "actions": [{"application": "notepad_sandbox", "operation": "create_document",
                     "arguments": {"name": "note.txt", "content": "hello"}}],
    })
    result = runtime.process(payload)
    body = json.loads(result.response)
    assert body["validation"]["valid"] is True
    assert body["executed"] is False
    assert not (tmp_path / ".fermion_control" / "NotepadSandbox" / "note.txt").exists()


def test_chat_executes_an_approved_control_plane_plan(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    payload = json.dumps({
        "summary": "Create a sandbox note.",
        "requires_approval": True,
        "actions": [{"application": "notepad_sandbox", "operation": "create_document",
                     "arguments": {"name": "note.txt", "content": "hello"}}],
    })
    body = runtime.submit_bridge(payload, approved=True)
    assert body["executed"] is True
    assert (tmp_path / ".fermion_control" / "NotepadSandbox" / "note.txt").read_text(encoding="utf-8") == "hello"


def test_chat_rejects_unknown_application_without_subprocess(tmp_path: Path) -> None:
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    payload = json.dumps({
        "actions": [{"application": "bettercap", "operation": "start", "arguments": {}}],
    })
    body = runtime.submit_bridge(payload, approved=True)
    assert body["validation"]["valid"] is False
    assert body["executed"] is False


def test_vendor_inventory_lists_excluded_trees_and_does_not_launch(tmp_path: Path) -> None:
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("List excluded vendors", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "vendor_inventory", "operation": "list_excluded", "arguments": {}}],
    }))
    report = plane.execute(plan, approved=True)
    assert report.validation.valid
    entries = report.records[0].result.details["entries"]
    names = {item["name"] for item in entries}
    assert "bettercap" in names and "codex" in names and "hackingtool" in names
    assert all(item["integration_status"] == "excluded_not_an_adapter" for item in entries)
    assert report.records[0].result.details["launched"] is False


def test_science_adapter_does_not_register_cp10_full(tmp_path: Path) -> None:
    plane = default_control_plane(tmp_path)
    spec = plane._applications["fermion_science"].specification("full")
    assert spec is None
    assert plane._applications["fermion_science"].specification("verify_cp10_bundle") is not None
