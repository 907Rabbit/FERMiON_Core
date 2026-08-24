from __future__ import annotations

import json

from fermion.adapters.llama_cpp import LlamaCppAdapter, LlamaCppConfig
from fermion.curriculum import CurriculumConfig, CurriculumRunner, StageStatus, challenger_promotable


def test_llama_adapter_parses_candidates_without_trusting_labels():
    text = 'prefix [{"id":"a","source":"pass","declared_artifacts":[]}] suffix'
    candidates = LlamaCppAdapter._parse(text, 3)
    assert len(candidates) == 1 and candidates[0].provenance == "llama.cpp"


def test_llama_source_mode_extracts_code_and_declared_artifacts(tmp_path):
    source = LlamaCppAdapter._extract_python(
        'Here is the program:\n```python\nimport json\njson.dump({"x":1}, open("result.json", "w"))\n```')
    assert source.startswith("import json")
    assert LlamaCppAdapter._infer_artifacts(source) == ("result.json",)
    config_path = tmp_path / "local.json"
    config_path.write_text(json.dumps({"llama_cpp": {"candidate_mode": "source", "port": 9090}}))
    config = LlamaCppConfig.from_file(config_path)
    assert config.candidate_mode == "source" and config.port == 9090


def test_llama_runtime_accepts_openai_compatible_models_health(monkeypatch):
    from fermion.adapters.llama_cpp import LlamaServerRuntime

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    attempts = []

    def fake_urlopen(request, timeout):
        attempts.append(request.full_url)
        if request.full_url.endswith("/health"):
            return Response({"error": "unsupported"})
        return Response({"data": [{"id": "local-model"}]})

    monkeypatch.setattr("fermion.adapters.llama_cpp.urllib.request.urlopen", fake_urlopen)
    runtime = LlamaServerRuntime(LlamaCppConfig(port=1234))
    assert runtime.health()
    assert runtime.status().configured
    assert attempts[-1].endswith("/v1/models")


def test_local_curriculum_integrity_memory_and_execution_stages_pass():
    runner = CurriculumRunner(CurriculumConfig(quick=True))
    assert runner.stage0().status == StageStatus.PASSED
    assert runner.stage3().status == StageStatus.PASSED
    assert runner.stage4().status == StageStatus.PASSED
    assert runner.stage5().status == StageStatus.SKIPPED
    assert runner.stage6().status == StageStatus.SKIPPED


def test_champion_promotion_hard_gates_override_score():
    champion = {"aggregate_score": 1.0, "undeclared_modifications": 0.0}
    better = {"aggregate_score": 2.0, "undeclared_modifications": 0.0}
    unsafe = {"aggregate_score": 3.0, "undeclared_modifications": 1.0}
    assert challenger_promotable(champion, better)
    assert not challenger_promotable(champion, unsafe)
