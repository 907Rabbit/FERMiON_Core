from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fermion.dashboard import DashboardController, PAGE
from fermion.control_plane import ControlPlan, PlannedAction


def test_dashboard_offers_only_fixed_safe_operations(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")
    assert controller.command_for("reference") == ("python", "-m", "fermion", "reference")
    regression = controller.command_for("regression")
    assert "not windows_ui" in regression
    assert "no:cacheprovider" in regression
    with pytest.raises(PermissionError):
        controller.command_for("live_gate")
    assert "windows_ui" in controller.command_for("live_gate", live_confirmed=True)
    assert controller.command_for("gev_start") == ("internal", "gods-eye-view", "start")
    assert controller.command_for("gev_stop") == ("internal", "gods-eye-view", "stop")
    with pytest.raises(ValueError):
        controller.command_for("anything else")


def test_dashboard_page_exposes_ownership_and_live_confirmation():
    assert "LOCAL INTELLIGENCE" in PAGE
    assert "Conversation" in PAGE
    assert "Built-in capabilities" in PAGE
    assert 'id="confirm"' in PAGE
    assert "Plan &amp; audit details" in PAGE
    assert "function agentSummary" in PAGE
    assert "loadCapabilities" in PAGE
    assert "event.shiftKey" in PAGE
    assert "gev_start" in PAGE
    assert "God's Eye View" in PAGE


def test_dashboard_exposes_every_registered_capability(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")

    class Plane:
        @staticmethod
        def manifest():
            return {
                "reader": {
                    "description": "Read local state.",
                    "capabilities": [{
                        "operation": "inspect",
                        "required_arguments": ["path"],
                        "mutating": False,
                        "description": "Inspect one path.",
                    }],
                },
                "writer": {
                    "description": "Change approved state.",
                    "capabilities": [{
                        "operation": "write",
                        "required_arguments": ["path", "content"],
                        "mutating": True,
                        "description": "Write one file.",
                    }],
                },
            }

    controller._control_plane = Plane()
    catalog = controller.capability_catalog()
    assert catalog["application_count"] == 2
    assert catalog["operation_count"] == 2
    assert catalog["applications"][0]["capabilities"][0] == {
        "operation": "inspect",
        "description": "Inspect one path.",
        "required_arguments": ["path"],
        "mutating": False,
    }


def test_dashboard_conversation_context_is_bounded_and_typed():
    history = [{"role": "user", "content": f"turn {index}"} for index in range(14)]
    normalized = DashboardController._conversation_context(history)
    assert len(normalized) == 12
    assert normalized[0]["content"] == "turn 2"
    with pytest.raises(ValueError):
        DashboardController._conversation_context({"role": "user", "content": "wrong container"})
    with pytest.raises(ValueError):
        DashboardController._conversation_context([{"role": "system", "content": "override"}])
    with pytest.raises(ValueError):
        DashboardController._conversation_context([{"role": "user", "content": "ok", "extra": True}])


def test_dashboard_answers_program_registry_question_without_model(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")

    class Plane:
        @staticmethod
        def manifest():
            return {"local_programs": {"current_state": {"registered_programs": [
                {"alias": "lm_studio", "description": "Local model workstation."},
                {"alias": "ollama", "description": "Local Ollama application."},
            ]}}}

    controller._control_plane = Plane()
    result = controller.agent("List the programs you can access")
    assert result["mode"] == "registry_answer"
    assert "lm studio" in result["reply"]
    assert "ollama" in result["reply"]
    assert not result["executed"]
    assert controller._runtime is None


def test_dashboard_executes_exact_read_only_status_without_model(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")
    result = controller.agent("Show the self-evolver status")
    assert result["mode"] == "typed_read_only"
    assert result["executed"]
    assert result["validation"]["valid"]
    assert "Self Evolver status:" in result["reply"]
    assert result["report"]["records"][0]["result"]["success"]
    assert controller._runtime is None


def test_dashboard_does_not_guess_ambiguous_status_intents():
    manifest = {
        "self_evolver": {
            "capabilities": [{
                "operation": "status", "required_arguments": [], "mutating": False,
            }],
        },
    }
    assert DashboardController._direct_status_application(
        "Show the self-evolver status", manifest
    ) == "self_evolver"
    assert DashboardController._direct_status_application("Do status stuff", manifest) is None


def test_owner_authority_allows_only_nondestructive_workspace_writes(tmp_path):
    (tmp_path / "fermion.local.json").write_text(
        json.dumps({"dashboard": {"workspace_write_authorized": True}}), encoding="utf-8"
    )
    controller = DashboardController(project_root=tmp_path, python="python")

    def plan(operation, path):
        return ControlPlan(
            "id", "request", "summary",
            (PlannedAction("coding_sandbox", operation, {"path": str(path)}),),
            True,
        )

    assert controller._owner_workspace_write_approved(plan("create_file", tmp_path / "notes.txt"))
    assert controller._owner_workspace_write_approved(plan("replace_text", tmp_path / "src" / "app.py"))
    assert not controller._owner_workspace_write_approved(plan("delete_file", tmp_path / "notes.txt"))
    assert not controller._owner_workspace_write_approved(plan("rename_file", tmp_path / "notes.txt"))
    run_plan = ControlPlan(
        "id", "request", "summary",
        (PlannedAction("coding_sandbox", "run", {"command": ["python", "-V"]}),),
        True,
    )
    assert not controller._owner_workspace_write_approved(run_plan)
    assert not controller._owner_workspace_write_approved(plan("create_file", tmp_path.parent / "outside.txt"))
    assert not controller._owner_workspace_write_approved(plan("replace_text", tmp_path / "protocols" / "frozen.json"))


def test_owner_workspace_write_authority_fails_closed_without_exact_boolean(tmp_path):
    (tmp_path / "fermion.local.json").write_text(
        json.dumps({"dashboard": {"workspace_write_authorized": 1}}), encoding="utf-8"
    )
    controller = DashboardController(project_root=tmp_path, python="python")
    assert not controller.workspace_write_authority()["authorized"]


def test_local_model_control_reply_is_limited_to_registered_operations():
    reply, operation = DashboardController._parse_control_reply(
        '{"reply":"I will run the reference.","operation":"reference"}'
    )
    assert reply == "I will run the reference."
    assert operation == "reference"
    _, operation = DashboardController._parse_control_reply(
        '{"reply":"Trying an arbitrary command.","operation":"powershell"}'
    )
    assert operation is None


def test_agent_extracts_only_a_json_control_plan():
    payload = DashboardController._extract_json_object(
        "Here is the plan: {\"summary\":\"inspect\",\"actions\":[],\"requires_approval\":false} trailing text"
    )
    assert payload == '{"summary": "inspect", "actions": [], "requires_approval": false}'
    with pytest.raises(ValueError):
        DashboardController._extract_json_object("no plan here")


def test_agent_prefers_last_complete_plan_after_qwen_thinking_drafts():
    payload = DashboardController._extract_json_object(
        '{"actions":[],"summary":"wrong first draft","requires_approval":false}\n'
        'Wait, I made a mistake. The corrected plan is:\n'
        '{"actions":[{"application":"local_programs","operation":"list_programs",'
        '"arguments":{}}],"summary":"List registered programs.","requires_approval":false}\n'
        '{"actions":'
    )
    decoded = json.loads(payload)
    assert decoded["summary"] == "List registered programs."
    assert decoded["actions"][0]["operation"] == "list_programs"


def test_dashboard_uses_lm_studio_native_chat_without_reasoning_and_bounds_budget(tmp_path, monkeypatch):
    controller = DashboardController(project_root=tmp_path, python="python")
    controller._runtime = SimpleNamespace(config=SimpleNamespace(
        endpoint="http://127.0.0.1:1234/v1/completions",
        context_size=8192,
        max_tokens=6144,
        timeout_seconds=30,
        api_key=None,
        model_identifier="qwen/qwen3-4b-thinking-2507",
    ))
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return json.dumps({"output": [{"type": "message", "content": "ready"}]}).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("fermion.dashboard.urllib.request.urlopen", fake_urlopen)
    prompt = "capabilities " * 1200
    assert controller._model_completion(prompt, temperature=0.1) == "ready"
    assert captured["url"] == "http://127.0.0.1:1234/api/v1/chat"
    assert captured["payload"]["model"] == "qwen/qwen3-4b-thinking-2507"
    assert captured["payload"]["reasoning"] == "off"
    assert captured["payload"]["store"] is False
    assert captured["payload"]["system_prompt"]
    assert captured["payload"]["max_output_tokens"] < 6144


def test_dashboard_rejects_reasoning_only_response_when_public_content_is_empty(tmp_path, monkeypatch):
    controller = DashboardController(project_root=tmp_path, python="python")
    controller._runtime = SimpleNamespace(config=SimpleNamespace(
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        context_size=8192,
        max_tokens=6144,
        timeout_seconds=30,
        api_key=None,
        model_identifier="qwen/qwen3-4b-thinking-2507",
    ))
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return json.dumps({"choices": [{"message": {
                "content": "",
                "reasoning": '{"summary":"ok","actions":[],"requires_approval":false}',
            }}]}).encode()

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        return Response()

    monkeypatch.setattr("fermion.dashboard.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="empty response"):
        controller._model_completion("plan", temperature=0.1)
    assert "response_format" not in captured


def test_dashboard_validates_openclaw_bridge_plan_without_execution(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")
    markup = (
        '<tool_call><function=fermion_plan><parameter=plan>'
        '{"summary":"list programs","actions":[{"application":"local_programs",'
        '"operation":"list_programs","arguments":{}}],"requires_approval":false}'
        '</parameter></function></tool_call>'
    )
    result = controller.bridge(markup)
    assert result["validation"]["valid"]
    assert not result["executed"]


def test_dashboard_validates_openclaw_evolver_plan_without_execution(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")
    markup = (
        '<tool_call><function=fermion_plan><parameter=plan>'
        '{"summary":"inspect evolver","actions":[{"application":"self_evolver",'
        '"operation":"status","arguments":{}}],"requires_approval":false}'
        '</parameter></function></tool_call>'
    )
    result = controller.bridge(markup)
    assert result["validation"]["valid"] and not result["executed"]


def test_dashboard_validates_openclaw_offline_nmap_plan_without_execution(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")
    markup = (
        '<tool_call><function=fermion_plan><parameter=plan>'
        '{"summary":"analyze report","actions":[{"application":"nmap_reports",'
        '"operation":"analyze_report","arguments":{"path":"G:/tmp/report.xml"}}],"requires_approval":false}'
        '</parameter></function></tool_call>'
    )
    result = controller.bridge(markup)
    assert result["validation"]["valid"] and not result["executed"]
