from __future__ import annotations

import pytest

from fermion.dashboard import DashboardController, PAGE


def test_dashboard_offers_only_fixed_safe_operations(tmp_path):
    controller = DashboardController(project_root=tmp_path, python="python")
    assert controller.command_for("reference") == ("python", "-m", "fermion", "reference")
    regression = controller.command_for("regression")
    assert "not windows_ui" in regression
    assert "no:cacheprovider" in regression
    with pytest.raises(PermissionError):
        controller.command_for("live_gate")
    assert "windows_ui" in controller.command_for("live_gate", live_confirmed=True)
    with pytest.raises(ValueError):
        controller.command_for("anything else")


def test_dashboard_page_exposes_ownership_and_live_confirmation():
    assert "Local control console" in PAGE
    assert "ownership is EXCLUSIVE" in PAGE
    assert 'id="confirm"' in PAGE
    assert "Plan &amp; audit details" in PAGE
    assert "function agentSummary" in PAGE


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
        "Here is the plan: {\"summary\":\"inspect\",\"actions\":[]} trailing text"
    )
    assert payload == '{"summary": "inspect", "actions": []}'
    with pytest.raises(ValueError):
        DashboardController._extract_json_object("no plan here")


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
