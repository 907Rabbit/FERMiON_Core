from __future__ import annotations

import json
import hashlib
from io import BytesIO

from fermion.control_plane import default_control_plane


class _Headers(dict):
    def get_content_type(self):
        return self.get("content-type", "application/octet-stream")


class _Response:
    status = 200
    headers = _Headers({"content-type": "application/octet-stream"})

    def __init__(self, data: bytes):
        self.data = BytesIO(data)

    def read(self, size=-1):
        return self.data.read(size)

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_control_plane_executes_a_validated_notepad_plan(tmp_path):
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Create a note", json.dumps({
        "summary": "Create a sandbox note.", "requires_approval": True,
        "actions": [{"application": "notepad_sandbox", "operation": "create_document",
                     "arguments": {"name": "note.txt", "content": "Alpha"}},
                    {"application": "notepad_sandbox", "operation": "append_text",
                     "arguments": {"name": "note.txt", "text": " Beta"}}],
    }))
    report = plane.execute(plan, approved=True)
    assert report.validation.valid
    assert len(report.records) == 2
    assert (tmp_path / "NotepadSandbox" / "note.txt").read_text(encoding="utf-8") == "Alpha Beta"


def test_control_plane_rejects_unknown_capabilities_without_execution(tmp_path):
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Do something", json.dumps({
        "actions": [{"application": "notepad_sandbox", "operation": "run_powershell", "arguments": {}}],
    }))
    report = plane.execute(plan, approved=True)
    assert not report.validation.valid
    assert not report.records


def test_control_plane_requires_user_approval(tmp_path):
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Create a note", json.dumps({
        "requires_approval": True,
        "actions": [{"application": "notepad_sandbox", "operation": "create_document",
                     "arguments": {"name": "note.txt"}}],
    }))
    report = plane.execute(plan, approved=False)
    assert not report.validation.valid
    assert "approval" in report.validation.reasons[0]


def test_control_plane_manifest_includes_current_registered_adapter_state(tmp_path):
    plane = default_control_plane(tmp_path)
    manifest = plane.manifest()
    assert "notepad_sandbox" in manifest and "coding_sandbox" in manifest and "self_evolver" in manifest and "nmap_reports" in manifest and "local_programs" in manifest
    assert "llama_runtime" in manifest and "fermion_science" in manifest and "vendor_inventory" in manifest
    assert "ciphey" in manifest and "bettercap" in manifest and "codex" in manifest
    assert "current_state" in manifest["local_programs"]
    assert "C:" in manifest["notepad_sandbox"]["description"]
    assert "No run" in manifest["coding_sandbox"]["description"]
    assert manifest["self_evolver"]["current_state"]["initialized"] is False
    assert "cannot run Nmap" in manifest["nmap_reports"]["description"]


def test_control_plane_evolver_requires_approval_and_records_a_bounded_run(tmp_path):
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Evolve the generated strategy", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "self_evolver", "operation": "evolve", "arguments": {
            "seed": 42, "generations": 8, "population": 16, "minimum_improvement": 0.001,
        }}],
    }))
    assert not plane.execute(plan, approved=False).validation.valid
    report = plane.execute(plan, approved=True)
    assert report.validation.valid and report.records[0].result.success
    assert report.records[0].result.details["executed"] is False
    assert (tmp_path / "SelfEvolver" / "audit.jsonl").is_file()


def test_control_plane_requires_approval_and_audits_a_verified_download(tmp_path, monkeypatch):
    data = b"approved download"
    expected_sha256 = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr("fermion.adapters.internet.socket.getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 0))])
    monkeypatch.setattr("fermion.adapters.internet.urlopen", lambda *_args, **_kwargs: _Response(data))
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Download the approved file", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "internet", "operation": "download_url", "arguments": {
            "url": "https://example.com/file.bin", "filename": "file.bin", "expected_sha256": expected_sha256,
        }}],
    }))
    denied = plane.execute(plan, approved=False)
    assert not denied.validation.valid and "approval" in denied.validation.reasons[0]

    report = plane.execute(plan, approved=True)
    assert report.validation.valid and report.records[0].result.details["sha256_verified"]
    assert (tmp_path / "downloads" / "file.bin").read_bytes() == data
    verified = [entry for entry in plane.audit.read() if entry["event"] == "download_verified"]
    assert verified[-1]["payload"] == {
        "plan_id": plan.plan_id, "url": "https://example.com/file.bin", "path": str(tmp_path / "downloads" / "file.bin"),
        "sha256": expected_sha256, "expected_sha256": expected_sha256, "executed": False,
    }
