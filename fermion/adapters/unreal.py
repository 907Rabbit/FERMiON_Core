"""Unreal command-line Python adapter with explicit project scoping."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


@dataclass(frozen=True)
class UnrealConfig:
    editor_cmd: Path
    project_file: Path
    timeout_seconds: float = 300.0


@dataclass(frozen=True)
class UnrealRun:
    return_code: int | None
    stdout: str
    stderr: str
    timed_out: bool


class UnrealAdapter:
    def __init__(self, config: UnrealConfig):
        self.config = config
        if not config.editor_cmd.is_file():
            raise ValueError(f"Unreal command executable not found: {config.editor_cmd}")
        if not config.project_file.is_file() or config.project_file.suffix.lower() != ".uproject":
            raise ValueError(f"Unreal project not found: {config.project_file}")

    def run_python(self, source: str) -> UnrealRun:
        with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as stream:
            stream.write(source); script = Path(stream.name)
        command = [str(self.config.editor_cmd), str(self.config.project_file), "-run=pythonscript",
                   f"-script={script}", "-unattended", "-nop4", "-nosplash"]
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=self.config.timeout_seconds)
            return UnrealRun(completed.returncode, completed.stdout, completed.stderr, False)
        except subprocess.TimeoutExpired as error:
            return UnrealRun(None, str(error.stdout or ""), str(error.stderr or ""), True)
        finally:
            script.unlink(missing_ok=True)


class UnrealPythonRunner(Protocol):
    def run_python(self, source: str) -> UnrealRun: ...


class UnrealEditorAdapter(ApplicationInterface):
    """Narrow, structured Unreal editor adapter for the generic application kernel.

    It deliberately invokes Unreal Python/editor APIs rather than GUI automation.
    Mutating commands are denied unless explicitly enabled in configuration.
    """

    _MARKER = "FERMION_UNREAL_JSON:"
    _CAPABILITIES = (
        CapabilityDefinition("observe", False, True, "Inspect current map, actors, components, and logs."),
        CapabilityDefinition("create_actor", True, True, "Spawn an actor with an optional label."),
        CapabilityDefinition("delete_actor", True, True, "Destroy an actor by editor label."),
        CapabilityDefinition("move_actor", True, True, "Set an actor location by editor label."),
        CapabilityDefinition("rename_actor", True, True, "Set an actor label."),
        CapabilityDefinition("set_property", True, True, "Set an exposed editor property."),
        CapabilityDefinition("save", False, True, "Save dirty editor packages."),
        CapabilityDefinition("capture_screenshot", False, True, "Capture auxiliary editor visual evidence."),
    )
    _MUTATING = {"create_actor", "delete_actor", "move_actor", "rename_actor", "set_property", "save"}

    def __init__(self, runner: UnrealPythonRunner, *, allow_mutations: bool = False):
        self.runner = runner
        self.allow_mutations = allow_mutations
        self._last_observation: Observation | None = None

    @classmethod
    def from_config(cls, config: UnrealConfig, *, allow_mutations: bool = False) -> "UnrealEditorAdapter":
        return cls(UnrealAdapter(config), allow_mutations=allow_mutations)

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("unreal-editor", self._CAPABILITIES)

    @staticmethod
    def _source(operation: str, arguments: dict[str, Any]) -> str:
        payload = json.dumps(arguments, sort_keys=True)
        return f'''import json
import unreal
payload = json.loads({payload!r})
def emit(value):
    print("FERMION_UNREAL_JSON:" + json.dumps(value, sort_keys=True, default=str))
def actors():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return subsystem.get_all_level_actors()
def actor(label):
    return next((item for item in actors() if item.get_actor_label() == label), None)
try:
    operation = {operation!r}
    if operation == "observe":
        world = unreal.EditorLevelLibrary.get_editor_world()
        current = actors()
        assets = unreal.EditorAssetLibrary.list_assets("/Game", True, False)
        emit({{"success": True, "state": {{"map": world.get_path_name() if world else None,
             "maps": [item for item in assets if item.endswith(".umap")],
             "actors": [{{"label": item.get_actor_label(), "class": item.get_class().get_name(),
                          "location": list(item.get_actor_location()),
                          "components": [component.get_name() for component in item.get_components_by_class(unreal.ActorComponent)]}}
                        for item in current]}}}})
    elif operation == "create_actor":
        klass = unreal.load_class(None, payload.get("class_path", "/Script/Engine.Actor"))
        item = unreal.EditorLevelLibrary.spawn_actor_from_class(klass, unreal.Vector(*payload.get("location", [0, 0, 0])))
        if payload.get("label"): item.set_actor_label(payload["label"])
        emit({{"success": True, "actor": item.get_actor_label()}})
    elif operation == "delete_actor":
        item = actor(payload["label"])
        emit({{"success": bool(item and unreal.EditorLevelLibrary.destroy_actor(item))}})
    elif operation == "move_actor":
        item = actor(payload["label"]); item.set_actor_location(unreal.Vector(*payload["location"]), False, False)
        emit({{"success": True, "location": list(item.get_actor_location())}})
    elif operation == "rename_actor":
        item = actor(payload["label"]); item.set_actor_label(payload["new_label"])
        emit({{"success": True, "label": item.get_actor_label()}})
    elif operation == "set_property":
        item = actor(payload["label"]); item.set_editor_property(payload["property"], payload["value"])
        emit({{"success": True, "value": str(item.get_editor_property(payload["property"]))}})
    elif operation == "save":
        emit({{"success": bool(unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True))}})
    elif operation == "capture_screenshot":
        unreal.AutomationLibrary.take_high_res_screenshot(int(payload.get("width", 1280)), int(payload.get("height", 720)), payload.get("path", "fermion.png"))
        emit({{"success": True, "path": payload.get("path", "fermion.png")}})
    else:
        emit({{"success": False, "error": "undeclared capability"}})
except Exception as error:
    emit({{"success": False, "error": type(error).__name__ + ": " + str(error)}})
'''

    def _invoke(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        run = self.runner.run_python(self._source(operation, arguments))
        if run.timed_out:
            return {"success": False, "error": "Unreal command timed out", "stderr": run.stderr}
        for line in reversed(run.stdout.splitlines()):
            if line.startswith(self._MARKER):
                try:
                    return json.loads(line[len(self._MARKER):])
                except json.JSONDecodeError:
                    break
        return {"success": False, "error": "Unreal adapter produced no structured response",
                "return_code": run.return_code, "stderr": run.stderr}

    def observe(self) -> Observation:
        response = self._invoke("observe", {})
        state = response.get("state", {}) if response.get("success") else {"error": response.get("error")}
        observation = Observation(__import__("time").time(), "unreal-editor", state,
                                  {"logs": response.get("stderr", ""), "screenshot": None})
        self._last_observation = observation
        return observation

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        if action.operation in self._MUTATING and not self.allow_mutations:
            return ActionResult(action.action_id, False, False, error="mutating Unreal actions are disabled")
        response = self._invoke(action.operation, action.arguments)
        return ActionResult(action.action_id, bool(response.get("success")), bool(response.get("success")),
                            {key: value for key, value in response.items() if key not in {"success", "error"}},
                            response.get("error"))

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observation = self.observe()
        if not result.success:
            return VerificationResult(False, expected_effect, observation.state, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observation.state)
        matches = all(observation.state.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observation.state,
                                  "" if matches else "Unreal post-state differs from expectation")

    def checkpoint(self) -> Checkpoint:
        observation = self.observe()
        digest = __import__("hashlib").sha256(json.dumps(observation.state, sort_keys=True).encode()).hexdigest()
        return Checkpoint(__import__("uuid").uuid4().hex, observation.state, digest, observation.timestamp)

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        # A generic editor snapshot cannot promise exact restoration; adapters may add a project-specific strategy.
        current = self.observe()
        digest = __import__("hashlib").sha256(json.dumps(current.state, sort_keys=True).encode()).hexdigest()
        return RollbackResult(False, checkpoint.checkpoint_id, digest,
                              "exact Unreal rollback requires a project-specific source-control or snapshot strategy")
