import json

import pytest

from fermion.cognitive.integration_registry import FirstPartyManifest, ProvenanceRegistry
from fermion.cognitive.integration_runtime import FermionRuntime, PerceptionEvent
from fermion.control_plane import default_control_plane


def runtime(tmp_path):
    source = tmp_path / "source"
    (source / "fermion").mkdir(parents=True)
    (source / "fermion" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "configs").mkdir()
    (source / "configs" / "gate.json").write_text("{}\n", encoding="utf-8")
    (source / "scripts").mkdir()
    (source / "scripts" / "launch.ps1").write_text("Write-Output safe\n", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='source'\n", encoding="utf-8")
    return FermionRuntime(
        control_plane=default_control_plane(tmp_path / "control"),
        registry=ProvenanceRegistry(tmp_path / "artifacts" / "provenance.jsonl"),
        source_root=source,
        source_manifest=FirstPartyManifest.build(source),
    )


def test_runtime_plans_without_execution_and_records_an_authorized_observed_action(tmp_path):
    facade = runtime(tmp_path)
    planned = facade.plan(PerceptionEvent("user_text", "Create a note"), json.dumps({
        "requires_approval": True,
        "actions": [{"application": "notepad_sandbox", "operation": "create_document",
                     "arguments": {"name": "note.txt", "content": "evidence"}}],
    }))
    assert planned.validation.valid
    assert not (tmp_path / "control" / "NotepadSandbox" / "note.txt").exists()
    receipt = facade.authorize(planned, approved=True)
    assert receipt.report.validation.valid
    assert receipt.provenance.state == "action_completed"
    assert (tmp_path / "control" / "NotepadSandbox" / "note.txt").read_text() == "evidence"
    assert facade.registry.verify()


def test_runtime_preserves_approval_boundary_and_records_no_execution(tmp_path):
    facade = runtime(tmp_path)
    planned = facade.plan(PerceptionEvent("user_text", "Create a note"), json.dumps({
        "actions": [{"application": "notepad_sandbox", "operation": "create_document",
                     "arguments": {"name": "note.txt"}}],
    }))
    receipt = facade.authorize(planned, approved=False)
    assert not receipt.report.validation.valid
    assert receipt.provenance.state == "approval_required"
    assert not (tmp_path / "control" / "NotepadSandbox" / "note.txt").exists()
    assert facade.registry.verify()


def test_runtime_rejects_drifted_source_manifest_before_planning(tmp_path):
    source = tmp_path / "source"
    (source / "fermion").mkdir(parents=True)
    (source / "fermion" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "configs").mkdir(); (source / "configs" / "gate.json").write_text("{}\n", encoding="utf-8")
    (source / "scripts").mkdir(); (source / "scripts" / "launch.ps1").write_text("safe\n", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='source'\n", encoding="utf-8")
    manifest = FirstPartyManifest.build(source)
    (source / "fermion" / "core.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        FermionRuntime(control_plane=default_control_plane(tmp_path / "control"),
                       registry=ProvenanceRegistry(tmp_path / "artifacts" / "provenance.jsonl"),
                       source_root=source, source_manifest=manifest)


def test_runtime_rejects_unknown_tool_without_executing(tmp_path):
    facade = runtime(tmp_path)
    planned = facade.plan(PerceptionEvent("user_text", "Do an unknown thing"), json.dumps({
        "actions": [{"application": "unknown", "operation": "anything", "arguments": {}}],
    }))
    receipt = facade.authorize(planned, approved=True)
    assert not receipt.report.validation.valid
    assert receipt.provenance.state == "action_rejected"
    assert facade.registry.verify()
