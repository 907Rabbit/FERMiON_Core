from __future__ import annotations

import hashlib
import json

import pytest

from fermion.system_prompt import FERMION_RUNTIME_BOUNDARY, load_system_prompt


def test_configured_system_prompt_is_hash_bound_and_keeps_runtime_boundary(tmp_path):
    prompt = tmp_path / "prompt.mkd"
    prompt.write_text("Owner-selected system behavior.", encoding="utf-8")
    digest = hashlib.sha256(prompt.read_bytes()).hexdigest().upper()
    (tmp_path / "fermion.local.json").write_text(json.dumps({
        "llm_system_prompt": {"path": "prompt.mkd", "sha256": digest.lower()},
    }), encoding="utf-8")
    loaded = load_system_prompt(tmp_path)
    assert loaded.configured is True
    assert loaded.sha256 == digest
    assert loaded.content.startswith("Owner-selected system behavior.")
    assert loaded.content.endswith(FERMION_RUNTIME_BOUNDARY)


def test_system_prompt_rejects_hash_mismatch_and_path_escape(tmp_path):
    prompt = tmp_path / "prompt.mkd"
    prompt.write_text("prompt", encoding="utf-8")
    (tmp_path / "fermion.local.json").write_text(json.dumps({
        "llm_system_prompt": {"path": "prompt.mkd", "sha256": "0" * 64},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_system_prompt(tmp_path)
    (tmp_path / "fermion.local.json").write_text(json.dumps({
        "llm_system_prompt": {"path": "../outside.mkd"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="project root"):
        load_system_prompt(tmp_path)
