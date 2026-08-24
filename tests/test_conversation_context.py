from fermion.cognitive.runtime import CognitiveRuntime,RuntimeConfig
def test_followup_uses_non_authoritative_active_conversation_context(tmp_path):
    runtime=CognitiveRuntime(RuntimeConfig(root=tmp_path));runtime.process("Compare carbon fiber and 3D printed drone frames.")
    result=runtime.process("Audit your previous answer about the drone-frame comparison.")
    assert result.reasoning["conversation_context"]["source_type"] == "conversation_context"
    assert result.reasoning["conversation_context"]["authoritative"] is False
def test_new_session_has_no_conversation_context(tmp_path):
    result=CognitiveRuntime(RuntimeConfig(root=tmp_path)).process("Audit your previous answer about the drone-frame comparison.")
    assert "conversation_context" not in result.reasoning
