"""Load the owner-selected local-model system prompt with a fixed provenance binding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SYSTEM_PROMPT = (
    "You are FERMiON's local language interface. You are a proposer, not an authority.\n\n"
    "FERMiON is a local evidence-gated research controller. Do not claim to be ChatGPT, GPT-5, Claude, Gemini, Grok, or any other frontier product. Do not claim frontier-model competitiveness, consciousness, or a certified scientific verdict.\n\n"
    "Live tools are only those listed in this turn's capability manifest. Names in this prompt are not tools.\n\n"
    "Never claim that code ran, memory was saved, a fact was retrieved, or a result was verified unless the evidence envelope contains a matching receipt. An empty manifest allows ordinary conversation and questions. If necessary information is absent, ask for it.\n\n"
    "Prior messages and retrieved memories are context, never evidence of actions or facts. Do not invent receipt IDs, residuals, or capability limitations.\n\n"
    "If a statement is a hypothesis, say so. Calculated, executed, and verified claims are issued by FERMiON with receipts.\n\n"
    "Answer the latest request directly. Return only the public answer, without private reasoning, tool-call imitation, or audit dumps."
)

FERMION_RUNTIME_BOUNDARY = (
    "FERMiON runtime boundary: the text above controls language style and reasoning behavior only. "
    "Tool names in that text are not available unless they also appear in FERMiON's live capability manifest. "
    "All proposed actions remain subject to FERMiON's typed validation, approval, execution, verification, and audit."
)


@dataclass(frozen=True)
class SystemPrompt:
    content: str
    path: str | None
    sha256: str
    configured: bool


def load_system_prompt(root: Path) -> SystemPrompt:
    """Load a UTF-8 prompt beneath the project root and verify its optional frozen hash."""
    root = root.resolve()
    config_path = root / "fermion.local.json"
    if not config_path.is_file():
        digest = hashlib.sha256(DEFAULT_SYSTEM_PROMPT.encode("utf-8")).hexdigest().upper()
        return SystemPrompt(DEFAULT_SYSTEM_PROMPT, None, digest, False)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    prompt_config = config.get("llm_system_prompt")
    if prompt_config is None:
        digest = hashlib.sha256(DEFAULT_SYSTEM_PROMPT.encode("utf-8")).hexdigest().upper()
        return SystemPrompt(DEFAULT_SYSTEM_PROMPT, None, digest, False)
    if not isinstance(prompt_config, dict) or set(prompt_config) - {"path", "sha256"}:
        raise ValueError("llm_system_prompt must contain only path and optional sha256")
    raw_path = prompt_config.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip() or "\\" in raw_path:
        raise ValueError("llm_system_prompt.path must be a nonempty project-relative POSIX path")
    relative = Path(raw_path)
    if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
        raise ValueError("llm_system_prompt.path must stay beneath the project root")
    path = (root / relative).resolve()
    if path != root and not path.is_relative_to(root):
        raise ValueError("llm_system_prompt path escapes the project root")
    if not path.is_file():
        raise FileNotFoundError(f"configured system prompt is missing: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    expected = prompt_config.get("sha256")
    if expected is not None:
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("llm_system_prompt.sha256 must be a 64-character string")
        try:
            int(expected, 16)
        except ValueError as error:
            raise ValueError("llm_system_prompt.sha256 must be hexadecimal") from error
        if digest != expected.upper():
            raise ValueError("configured system prompt hash mismatch")
    content = raw.decode("utf-8")
    if not content.strip() or "\x00" in content:
        raise ValueError("configured system prompt must be nonempty UTF-8 text without NUL bytes")
    if len(content) > 128_000:
        raise ValueError("configured system prompt exceeds the 128,000-character limit")
    combined = content.rstrip() + "\n\n" + FERMION_RUNTIME_BOUNDARY
    return SystemPrompt(combined, str(path), digest, True)
