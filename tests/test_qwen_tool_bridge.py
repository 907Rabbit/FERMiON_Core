import pytest

from fermion.cognitive.tool_bridge import (ToolCallParseError, parse_qwen_xml_exec,
                                           parse_qwen_xml_plan, parse_qwen_bridge_plan, qwen_bridge_instruction)


def test_parses_single_qwen_xml_exec_call_as_a_proposal_only():
    proposal = parse_qwen_xml_exec(
        "<tool_call><function=exec><parameter=command>"
        "Get-ChildItem -Name | Select-Object -First 5"
        "</parameter></function></tool_call>"
    )
    assert proposal.tool == "exec"
    assert proposal.command == "Get-ChildItem -Name | Select-Object -First 5"
    assert proposal.source_format == "qwen_xml_reasoning"


@pytest.mark.parametrize("payload", [
    "<tool_call><function=exec><parameter=command></parameter></function></tool_call>",
    "before <tool_call><function=exec><parameter=command>dir</parameter></function></tool_call>",
    "<tool_call><function=exec><parameter=command>dir</parameter></function></tool_call> extra",
    "<tool_call><function=other><parameter=command>dir</parameter></function></tool_call>",
])
def test_rejects_ambiguous_or_unsupported_markup(payload):
    with pytest.raises(ToolCallParseError):
        parse_qwen_xml_exec(payload)


def test_decodes_text_but_rejects_nul_bytes():
    proposal = parse_qwen_xml_exec(
        "<tool_call><function=exec><parameter=command>echo A &amp; B</parameter></function></tool_call>"
    )
    assert proposal.command == "echo A & B"
    with pytest.raises(ToolCallParseError):
        parse_qwen_xml_exec(
            "<tool_call><function=exec><parameter=command>bad\x00command</parameter></function></tool_call>"
        )


def test_parses_declared_fermion_plan_but_not_prose_or_native_empty_call():
    plan = parse_qwen_xml_plan(
        '<tool_call><function=fermion_plan><parameter=plan>'
        '{"summary":"list","actions":[{"application":"local_programs","operation":"list_programs","arguments":{}}],"requires_approval":false}'
        '</parameter></function></tool_call>'
    )
    assert plan["actions"][0]["operation"] == "list_programs"
    with pytest.raises(ToolCallParseError):
        parse_qwen_xml_plan('<tool_call><function=exec><parameter=command>{}</parameter></function></tool_call>')
    instruction = qwen_bridge_instruction({"local_programs": {}})
    assert "Do not call native tools" in instruction
    assert "plain JSON object" in instruction
    assert "<tool_call>" not in instruction
    assert "local_programs" not in instruction


def test_normalizes_one_exact_typed_json_action_from_small_model():
    action = '{"application":"local_programs","operation":"list_programs","arguments":{},"requires_approval":false}'
    plan = parse_qwen_bridge_plan(action)
    assert plan["actions"] == [{"application": "local_programs", "operation": "list_programs", "arguments": {}}]
    assert not plan["requires_approval"]
    assert parse_qwen_bridge_plan("json  " + action) == plan
    assert parse_qwen_bridge_plan("```json\n" + action + "\n```") == plan
    assert parse_qwen_bridge_plan("`json  " + action + "`") == plan


def test_normalizes_qwen_wrapped_plan_json():
    wrapped = (
        '{"plan":{"summary":"List registered programs","actions":['
        '{"application":"local_programs","operation":"list_programs","arguments":{}}],'
        '"requires_approval":false}}'
    )
    plan = parse_qwen_bridge_plan("`json  " + wrapped + "`")
    assert plan["summary"] == "List registered programs"
    assert plan["actions"][0]["operation"] == "list_programs"
    assert plan["requires_approval"] is False


def test_normalizes_only_whitespace_split_schema_keys():
    plan = parse_qwen_bridge_plan(
        '{"summary":"list","actions":[{"ap plication":"local_programs",'
        '"ope ration":"list_programs","argumen ts":{}}],"requires_approval":false}'
    )
    assert plan["actions"] == [{"application": "local_programs", "operation": "list_programs", "arguments": {}}]


def test_repairs_only_terminal_display_escapes_before_strict_validation():
    plan = parse_qwen_bridge_plan(
        '{"summary":"list","actions":[{"ap plication":"local\\_programs",'
        '"ope ration":"list\\_programs","argumen\\\nts":{}}],"requires\\_approval":fal se}\\'
    )
    assert plan["requires_approval"] is False
    assert plan["actions"][0]["application"] == "local_programs"


def test_extracts_one_plan_from_copied_tui_status_text():
    copied = '''`json  {"summary":"list","actions":[{"application":"local_programs","operation":"list_programs","arguments":{}}],"requires_approval":false}`
connected | idle
agent crestodian | session example'''
    assert parse_qwen_bridge_plan(copied)["actions"][0]["operation"] == "list_programs"
