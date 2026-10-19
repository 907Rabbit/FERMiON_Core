from fermion.cognitive.runtime import CognitiveRuntime,RuntimeConfig
def test_followup_uses_non_authoritative_active_conversation_context(tmp_path):
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path));runtime.process("Compare carbon fiber and 3D printed drone frames.")
    result=runtime.process("Audit your previous answer about the drone-frame comparison.")
    assert result.reasoning["conversation_context"]["source_type"] == "conversation_context"
    assert result.reasoning["conversation_context"]["authoritative"] is False
def test_new_session_has_no_conversation_context(tmp_path):
    result=CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Audit your previous answer about the drone-frame comparison.")
    assert "conversation_context" not in result.reasoning


def test_ordinary_followup_gets_bounded_history_without_second_model_call(tmp_path, monkeypatch):
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    calls = []
    def verbalize(payload):
        calls.append(payload)
        return "A short description."
    monkeypatch.setattr(runtime.language, "interpret", lambda _: (_ for _ in ()).throw(AssertionError("redundant call")))
    monkeypatch.setattr(runtime.language, "verbalize", verbalize)
    runtime.process("Draft a description of Project Lantern.")
    result = runtime.process("Make it shorter.")
    assert len(calls) == 2
    assert calls[-1]["conversation_history"] == [
        {"role": "user", "content": "Draft a description of Project Lantern."},
        {"role": "assistant", "content": "A short description."}]
    assert result.reasoning["conversation_context"]["authoritative"] is False
    assert result.response == "A short description."
    assert result.timing["generated_tokens"] is None
    runtime.clear_conversation()
    runtime.process("What were we discussing?")
    assert calls[-1]["conversation_history"] == []


def test_prior_assistant_assertion_never_becomes_execution_authority(tmp_path, monkeypatch):
    runtime = CognitiveRuntime(RuntimeConfig(root=tmp_path))
    runtime.conversation_context = [{"user": "Was it executed?", "assistant": "The script ran successfully."}]
    monkeypatch.setattr(runtime.language, "verbalize", lambda _: "The script ran successfully.")
    result = runtime.process("Repeat that claim.")
    assert result.response.startswith("EVIDENCE_CLAIM_UNSUPPORTED")
    assert not runtime._evidence_envelope().receipts
