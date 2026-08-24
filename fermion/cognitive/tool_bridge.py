"""Compatibility boundary for local models that serialize tool calls as text.

Some LM Studio chat templates put Qwen-style calls in ``reasoning_content`` as
XML instead of returning an OpenAI ``tool_calls`` record.  This module turns
only one exact, declared representation into a *proposal*.  It deliberately
does not execute commands; execution remains owned by the FERMiON control
plane and its approval/audit path.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any


_QWEN_EXEC_CALL = re.compile(
    r"^\s*<tool_call>\s*<function=exec>\s*"
    r"<parameter=command>\s*(?P<command>.*?)\s*"
    r"</parameter>\s*</function>\s*</tool_call>\s*$",
    re.DOTALL,
)
_QWEN_FERMION_PLAN = re.compile(
    r"^\s*<tool_call>\s*<function=fermion_plan>\s*"
    r"<parameter=plan>\s*(?P<plan>.*?)\s*"
    r"</parameter>\s*</function>\s*</tool_call>\s*$",
    re.DOTALL,
)


@dataclass(frozen=True)
class ToolProposal:
    """A parsed request which still requires policy validation and approval."""

    tool: str
    command: str
    source_format: str = "qwen_xml_reasoning"


class ToolCallParseError(ValueError):
    """The model output is not the narrow, supported tool-call form."""


def qwen_bridge_instruction(manifest: dict[str, Any]) -> str:
    """Instruction for text-mode models; native OpenAI tool calls stay disabled.

    The returned text intentionally asks for a plan rather than a shell command.
    The plan remains subject to the normal control-plane capability validation.
    """
    return (
        "Do not call native tools. If an action is needed, return exactly one "
        "plain JSON object and no other text, markup, XML, or backticks. JSON "
        "must contain actions, summary, and requires_approval. Each action must "
        "use only the capability manifest supplied separately in the prompt."
    )


def parse_qwen_xml_exec(reasoning_content: str, *, max_command_chars: int = 8_000) -> ToolProposal:
    """Parse exactly one Qwen XML ``exec`` call without interpreting prose.

    Rejecting anything beyond this single form is intentional: model reasoning
    may contain examples, quoted markup, or multiple requests.  None of those
    are authorization to run a program.
    """

    if not isinstance(reasoning_content, str):
        raise ToolCallParseError("reasoning content must be text")
    match = _QWEN_EXEC_CALL.fullmatch(reasoning_content)
    if match is None:
        raise ToolCallParseError("unsupported or ambiguous Qwen tool-call markup")
    command = html.unescape(match.group("command")).strip()
    if not command:
        raise ToolCallParseError("tool call has an empty command")
    if "\x00" in command or len(command) > max_command_chars:
        raise ToolCallParseError("tool command violates the bridge boundary")
    return ToolProposal(tool="exec", command=command)


def parse_qwen_xml_plan(text: str, *, max_plan_chars: int = 16_000) -> dict[str, Any]:
    """Parse one explicit FERMiON control-plan request, never executable prose."""
    if not isinstance(text, str):
        raise ToolCallParseError("bridge text must be text")
    match = _QWEN_FERMION_PLAN.fullmatch(text)
    if match is None:
        raise ToolCallParseError("unsupported or ambiguous FERMiON plan markup")
    encoded = html.unescape(match.group("plan")).strip()
    if not encoded or len(encoded) > max_plan_chars:
        raise ToolCallParseError("FERMiON plan violates bridge boundary")
    try:
        plan = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise ToolCallParseError("FERMiON plan is not valid JSON") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("actions"), list):
        raise ToolCallParseError("FERMiON plan must contain an actions array")
    return plan


def parse_qwen_bridge_plan(text: str, *, max_plan_chars: int = 16_000) -> dict[str, Any]:
    """Accept a narrow text envelope from small models as a control proposal.

    Qwen commonly returns either a single action directly or ``{"plan": ...}``
    after being asked for a bridge plan.  Both forms stay proposal-only and are
    normalized before the control plane sees them.
    """
    try:
        return parse_qwen_xml_plan(text, max_plan_chars=max_plan_chars)
    except ToolCallParseError:
        pass
    if not isinstance(text, str) or len(text) > max_plan_chars:
        raise ToolCallParseError("bridge text violates boundary")
    normalized = text.strip()
    if normalized.startswith("`") and normalized.endswith("`") and not normalized.startswith("```"):
        normalized = normalized[1:-1].strip()
    if normalized.startswith("```json") and normalized.endswith("```"):
        normalized = normalized[7:-3].strip()
    elif normalized.startswith("json") and len(normalized) > 4 and normalized[4].isspace():
        normalized = normalized[4:].strip()
    # OpenClaw's terminal renderer may copy Markdown escapes and hard-wrap
    # continuations into the selected text.  These transformations repair only
    # invalid JSON display artifacts; values still undergo strict validation.
    normalized = re.sub(r"\\\r?\n", "", normalized)
    normalized = normalized.replace(r"\_", "_")
    normalized = re.sub(r"\\\s*$", "", normalized)
    normalized = re.sub(r"\bf\s*a\s*l\s*s\s*e\b", "false", normalized)
    normalized = re.sub(r"\bt\s*r\s*u\s*e\b", "true", normalized)
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as initial_error:
        # Copying from the TUI can include a ``json`` label, fences, and its
        # trailing connection-status line. Select one decodable object rather
        # than requiring the browser textarea to contain only that substring.
        decoder = json.JSONDecoder()
        value = None
        for index, character in enumerate(normalized):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(normalized[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                value = candidate
                break
        if value is None:
            raise ToolCallParseError("unsupported bridge markup or JSON") from initial_error
    def normalized_keys(item: object) -> object:
        """Repair display/model whitespace in known JSON keys, never values.

        Some local Qwen templates split tokens inside keys (``"ap plication"``).
        Normalizing only object keys keeps the plan schema strict: application
        aliases, operations, arguments, and every other value remain untouched
        for ordinary control-plane validation.
        """
        if isinstance(item, list):
            return [normalized_keys(entry) for entry in item]
        if not isinstance(item, dict):
            return item
        repaired: dict[str, object] = {}
        for key, entry in item.items():
            clean_key = re.sub(r"\s+", "", key)
            if clean_key in repaired:
                raise ToolCallParseError("bridge JSON has colliding normalized keys")
            repaired[clean_key] = normalized_keys(entry)
        return repaired

    value = normalized_keys(value)
    if isinstance(value, dict) and set(value) == {"plan"}:
        value = value["plan"]
    if isinstance(value, dict) and {"actions", "summary", "requires_approval"}.issubset(value):
        permitted_plan_fields = {"actions", "summary", "requires_approval"}
        if set(value) - permitted_plan_fields:
            raise ToolCallParseError("bridge plan JSON has unsupported fields")
        if not isinstance(value["summary"], str) or not isinstance(value["actions"], list):
            raise ToolCallParseError("bridge plan JSON is not typed")
        if not isinstance(value["requires_approval"], bool):
            raise ToolCallParseError("requires_approval must be boolean")
        for action in value["actions"]:
            if not isinstance(action, dict) or set(action) - {"application", "operation", "arguments"}:
                raise ToolCallParseError("bridge plan action has unsupported fields")
            if not isinstance(action.get("application"), str) or not isinstance(action.get("operation"), str):
                raise ToolCallParseError("bridge plan action is not typed")
            if not isinstance(action.get("arguments"), dict):
                raise ToolCallParseError("bridge plan action arguments must be an object")
        return value
    required = {"application", "operation", "arguments", "requires_approval"}
    if not isinstance(value, dict) or set(value) - required or not {"application", "operation", "arguments"}.issubset(value):
        raise ToolCallParseError("single-action bridge JSON has unsupported fields")
    if not isinstance(value["application"], str) or not isinstance(value["operation"], str) or not isinstance(value["arguments"], dict):
        raise ToolCallParseError("single-action bridge JSON is not typed")
    approval = value.get("requires_approval", True)
    if not isinstance(approval, bool):
        raise ToolCallParseError("requires_approval must be boolean")
    return {"summary": "", "actions": [{"application": value["application"], "operation": value["operation"], "arguments": value["arguments"]}], "requires_approval": approval}
