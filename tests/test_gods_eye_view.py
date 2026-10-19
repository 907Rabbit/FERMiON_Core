from __future__ import annotations

import json
from pathlib import Path
import pytest

from fermion.adapters.gods_eye_view import GodsEyeViewAdapter, GodsEyeViewRuntime, RELATIVE_APP
from fermion.control_plane import default_control_plane
from fermion.software.application import Action, ActionResult


def _fake_tree(root: Path) -> Path:
    tree = root / RELATIVE_APP
    vite = tree / "node_modules" / "vite" / "bin"
    vite.mkdir(parents=True)
    (vite / "vite.js").write_text("/* vite */\n", encoding="utf-8")
    return tree


def test_runtime_refuses_non_loopback_bind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="localhost"):
        GodsEyeViewRuntime(source_root=tmp_path, state_dir=tmp_path / "state", host="0.0.0.0")


def test_status_reports_missing_tree_without_launching(tmp_path: Path) -> None:
    runtime = GodsEyeViewRuntime(source_root=tmp_path, state_dir=tmp_path / "state")
    status = runtime.status(network=False)
    assert status.tree_present is False
    assert status.running is False
    assert status.healthy is False
    assert status.url == "http://127.0.0.1:4173/"


def test_start_launches_loopback_vite_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = _fake_tree(tmp_path)
    launched: dict[str, object] = {}
    ready = {"value": False}

    class FakeProcess:
        pid = 4242

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **kwargs):
        launched["command"] = command
        launched["kwargs"] = kwargs
        ready["value"] = True
        return FakeProcess()

    import subprocess as real_subprocess

    real_popen = real_subprocess.Popen

    def selective_popen(command, **kwargs):
        if command and str(command[0]).lower().endswith("node.exe"):
            return fake_popen(command, **kwargs)
        return real_popen(command, **kwargs)

    monkeypatch.setattr("fermion.adapters.gods_eye_view.shutil.which",
                        lambda name: r"C:\Program Files\nodejs\node.exe" if name == "node" else None)
    monkeypatch.setattr("fermion.adapters.gods_eye_view.subprocess.Popen", selective_popen)
    monkeypatch.setattr(GodsEyeViewRuntime, "health", lambda self, timeout=2.0: ready["value"])
    monkeypatch.setattr(GodsEyeViewRuntime, "_port_open", lambda self: False)
    monkeypatch.setattr(GodsEyeViewRuntime, "_process_exists", lambda self, pid: pid == 4242)

    runtime = GodsEyeViewRuntime(source_root=tmp_path, state_dir=tmp_path / "state")
    status = runtime.start()
    command = launched["command"]
    kwargs = launched["kwargs"]
    assert command[0].endswith("node.exe")
    assert command[1] == str((tree / "node_modules" / "vite" / "bin" / "vite.js").resolve())
    assert command[2:] == ["--host", "127.0.0.1", "--port", "4173", "--strictPort"]
    assert kwargs["cwd"] == str(tree)
    assert kwargs["env"]["HOST"] == "127.0.0.1"
    assert kwargs["env"]["PORT"] == "4173"
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert status.healthy is True
    assert (tmp_path / "state" / "gods-eye-view.pid").read_text(encoding="ascii") == "4242"


def test_start_fails_when_tree_is_missing(tmp_path: Path) -> None:
    adapter = GodsEyeViewAdapter(source_root=tmp_path, state_dir=tmp_path / "state")
    result = adapter.execute(Action("start", {}))
    assert result.success is False
    assert "missing" in (result.error or "").lower()


def test_control_plane_registers_localhost_lifecycle(tmp_path: Path) -> None:
    plane = default_control_plane(tmp_path)
    application = plane._applications["gods_eye_view"]
    assert application.specification("status") is not None
    assert application.specification("start").mutating is True
    assert application.specification("scan") is None
    assert "localhost" in application.description.lower()
    plan = plane.parse_plan("Globe status", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "gods_eye_view", "operation": "status", "arguments": {}}],
    }))
    report = plane.execute(plan, approved=True)
    assert report.validation.valid
    details = report.records[0].result.details
    assert details["host"] == "127.0.0.1"
    assert details["port"] == 4173


def test_start_requires_control_plane_approval(tmp_path: Path) -> None:
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Start the globe", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "gods_eye_view", "operation": "start", "arguments": {}}],
    }))
    denied = plane.execute(plan, approved=False)
    assert not denied.validation.valid
    assert "approval" in denied.validation.reasons[0]


def test_verify_rejects_non_loopback_details(tmp_path: Path) -> None:
    adapter = GodsEyeViewAdapter(source_root=tmp_path, state_dir=tmp_path / "state")
    result = ActionResult("id", True, False, {"host": "8.8.8.8", "port": 4173})
    verification = adapter.verify(result)
    assert verification.success is False
    assert "localhost" in verification.reason
