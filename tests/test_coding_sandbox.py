from __future__ import annotations

from fermion.adapters.coding import CodingSandboxAdapter, CodingSandboxConfig
from fermion.software.application import Action


def adapter(tmp_path, allowed):
    return CodingSandboxAdapter(CodingSandboxConfig(tmp_path / "CodingSandbox", (allowed,)))


def test_coding_sandbox_edits_nested_source_files_only_under_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    nested = allowed / "src"
    nested.mkdir(parents=True)
    item = adapter(tmp_path, allowed)
    source = nested / "program.py"
    created = item.execute(Action("create_file", {"path": str(source), "content": "print('safe')\n"}))
    assert created.success and not created.details["executed"]
    inspected = item.execute(Action("inspect_file", {"path": str(source)}))
    assert inspected.success and inspected.details["content"] == "print('safe')\n" and inspected.details["sha256"]
    outside = item.execute(Action("create_file", {"path": str(tmp_path / "outside.py"), "content": "no"}))
    assert not outside.success
    unsupported = item.execute(Action("create_file", {"path": str(nested / "run.exe"), "content": "no"}))
    assert not unsupported.success


def test_coding_sandbox_rolls_back_only_touched_files(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "program.py"
    source.write_text("before\n", encoding="utf-8")
    item = adapter(tmp_path, allowed)
    checkpoint = item.checkpoint()
    assert item.execute(Action("replace_text", {"path": str(source), "content": "after\n"})).success
    assert item.execute(Action("create_file", {"path": str(allowed / "new.py"), "content": "new\n"})).success
    assert item.rollback(checkpoint).success
    assert source.read_text(encoding="utf-8") == "before\n"
    assert not (allowed / "new.py").exists()


def test_coding_sandbox_never_launches_an_editor_without_explicit_configuration(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "program.py"
    source.write_text("pass\n", encoding="utf-8")
    result = adapter(tmp_path, allowed).execute(Action("open_in_editor", {"path": str(source)}))
    assert not result.success and result.error == "Editor launch is disabled"
