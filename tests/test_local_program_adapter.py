from __future__ import annotations

from pathlib import Path

from fermion.adapters.local_program import LocalProgramAdapter, ProgramEntry
from fermion.software.application import Action


def test_local_program_adapter_registers_and_launches_only_catalog_entries(tmp_path):
    executable = Path(r"C:\Windows\System32\where.exe")
    adapter = LocalProgramAdapter(tmp_path / "catalog.json", (executable.parent,),
                                  (ProgramEntry("where_tool", str(executable)),))
    listed = adapter.execute(Action("list_programs"))
    assert listed.success and listed.details["programs"][0]["alias"] == "where_tool"
    launched = adapter.execute(Action("launch_program", {"alias": "where_tool", "arguments": ["where"]}))
    assert launched.success
    assert adapter.execute(Action("close_program", {"process_id": launched.details["process_id"]})).success


def test_local_program_adapter_rejects_unknown_alias(tmp_path):
    adapter = LocalProgramAdapter(tmp_path / "catalog.json", (Path(r"C:\Windows\System32"),))
    result = adapter.execute(Action("launch_program", {"alias": "unknown"}))
    assert not result.success
