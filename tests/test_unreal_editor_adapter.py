from __future__ import annotations

from fermion.adapters.unreal import UnrealEditorAdapter, UnrealRun
from fermion.software.application import Action


class FakeUnrealRunner:
    def __init__(self, payload: dict | None = None):
        self.payload = payload or {"success": True, "state": {"map": "/Game/Test", "maps": ["/Game/Test.umap"], "actors": []}}
        self.sources: list[str] = []

    def run_python(self, source: str) -> UnrealRun:
        import json
        self.sources.append(source)
        return UnrealRun(0, "FERMION_UNREAL_JSON:" + json.dumps(self.payload), "", False)


def test_unreal_adapter_declares_constrained_editor_capabilities():
    adapter = UnrealEditorAdapter(FakeUnrealRunner())
    names = {item.name for item in adapter.capabilities().items}
    assert {"observe", "create_actor", "delete_actor", "move_actor", "save", "capture_screenshot"} <= names


def test_unreal_adapter_observation_is_structured_and_timestamped():
    adapter = UnrealEditorAdapter(FakeUnrealRunner())
    observation = adapter.observe()
    assert observation.timestamp > 0 and observation.state["map"] == "/Game/Test"


def test_unreal_adapter_defaults_to_read_only_mutation_guard():
    adapter = UnrealEditorAdapter(FakeUnrealRunner())
    result = adapter.execute(Action("create_actor", {"label": "Cube"}))
    assert not result.success and result.error == "mutating Unreal actions are disabled"


def test_unreal_adapter_generates_native_python_for_enabled_action():
    runner = FakeUnrealRunner({"success": True, "actor": "Cube"})
    result = UnrealEditorAdapter(runner, allow_mutations=True).execute(Action("create_actor", {"label": "Cube"}))
    assert result.success and "spawn_actor_from_class" in runner.sources[0]


def test_unreal_adapter_verifies_and_reports_structured_runner_failures():
    adapter = UnrealEditorAdapter(FakeUnrealRunner({"success": False, "error": "editor unavailable"}))
    result = adapter.execute(Action("observe"))
    verification = adapter.verify(result)
    assert not result.success and not verification.success and verification.reason == "editor unavailable"


def test_unreal_checkpoint_is_audit_safe_when_exact_rollback_is_unavailable():
    adapter = UnrealEditorAdapter(FakeUnrealRunner())
    checkpoint = adapter.checkpoint()
    rollback = adapter.rollback(checkpoint)
    assert checkpoint.logical_state["map"] == "/Game/Test"
    assert not rollback.success and "project-specific" in rollback.reason
