from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from fermion.hr.contracts import CandidateProgram
from fermion.hr.memory import EpisodicMemory, MemoryRecord
from fermion.hr.system import FermionHR
from fermion.software.capabilities import Capability, CapabilityRegistry
from fermion.software.executor import GuardedExecutor, PolicyViolation
from fermion.software.kernel import SoftwareLearningKernel
from fermion.software.observation import FileSystemProvider, ObservationBus
from fermion.software.recorder import ActionRecorder
from fermion.software.replay import ReplayDatabase
from fermion.software.skills import DemonstrationSkillCompiler
from fermion.software.validators import JSONValidator
from fermion.task import run_task


def candidate(source: str, identifier: str = "candidate") -> CandidateProgram:
    return CandidateProgram(identifier, source, declared_artifacts=("result.json",),
                            estimated_cost=0.1, estimated_risk=0.1)


def test_guarded_executor_rolls_back_by_default_and_commits_explicitly(tmp_path):
    validator = JSONValidator("result.json", ("answer",), {"answer": 42})
    program = candidate("import json\njson.dump({'answer':42},open('result.json','w'))")
    executor = GuardedExecutor(tmp_path)
    trial = executor.execute(program, validator)
    assert trial.validator.success == 1 and trial.recovered and not (tmp_path / "result.json").exists()
    committed = executor.execute(program, validator, commit=True)
    assert committed.committed and json.loads((tmp_path / "result.json").read_text())["answer"] == 42


def test_undeclared_changes_are_detected_and_never_successful(tmp_path):
    program = candidate("open('extra.txt','w').write('damage')\nopen('result.json','w').write('{}')")
    result = GuardedExecutor(tmp_path).execute(program, JSONValidator("result.json"))
    assert "extra.txt" in result.undeclared_artifacts
    assert result.validator.success == 0 and result.validator.contradiction == 1


def test_policy_rejects_dangerous_import_and_path_escape(tmp_path):
    executor = GuardedExecutor(tmp_path)
    with pytest.raises(PolicyViolation):
        executor.inspect(candidate("import subprocess"))
    with pytest.raises(PolicyViolation):
        executor.inspect(CandidateProgram("escape", "pass", declared_artifacts=("../x",)))


def test_memory_retrieval_survives_restart(tmp_path):
    path = tmp_path / "memory.db"; memory = EpisodicMemory(path)
    memory.write(MemoryRecord((1, 0), (2,), {}, {"method": "X"}, {}, {}, 1, 1, time.time()), threshold=0)
    memory.close(); memory = EpisodicMemory(path)
    assert memory.retrieve((1, 0))[0].record.action["method"] == "X"
    memory.close()


def test_demonstration_compiles_and_capability_tracks_evidence(tmp_path):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    bus = ObservationBus([FileSystemProvider(workspace)])
    recorder = ActionRecorder(tmp_path / "actions.jsonl")
    before = bus.observe(); (workspace / "x.txt").write_text("x"); after = bus.observe()
    recorder.record(before, {"type": "write"}, after)
    skill = DemonstrationSkillCompiler().compile("write-x", recorder.read(), "file_exists")
    assert skill.steps[0].expected_changes == ("x.txt",)
    registry = CapabilityRegistry(tmp_path / "capabilities.json")
    registry.put(Capability("write", "filesystem", "api"))
    assert registry.record_outcome("write", True).verified_successes == 1


def test_kernel_executes_validates_updates_and_freezes_replay(tmp_path):
    workspace = tmp_path / "workspace"; workspace.mkdir()
    replay = ReplayDatabase(tmp_path / "replay.db")
    memory = EpisodicMemory(tmp_path / "episodes.db")
    kernel = SoftwareLearningKernel(FermionHR(), ObservationBus([FileSystemProvider(workspace)]),
                                    GuardedExecutor(workspace), replay, memory)
    program = candidate("import json\njson.dump({'answer':42},open('result.json','w'))")
    result = kernel.run("write answer", [program], JSONValidator("result.json", ("answer",), {"answer": 42}))
    assert result.execution.validator.success == 1
    assert len(replay) == 1 and len(memory) == 1
    replay.close(); memory.close()


def test_declarative_task_runner_supports_dry_run_and_commit(tmp_path):
    spec = tmp_path / "task.json"
    spec.write_text(json.dumps({
        "goal": "write answer",
        "workspace": str(tmp_path),
        "candidates": [{"id": "only", "source": "import json\njson.dump({'answer':42},open('result.json','w'))",
                        "declared_artifacts": ["result.json"]}],
        "validator": {"type": "json", "path": "result.json", "expected": {"answer": 42}},
    }))
    dry = run_task(spec)
    assert dry.success == 1 and not dry.committed and not (tmp_path / "result.json").exists()
    committed = run_task(spec, commit=True)
    assert committed.committed and (tmp_path / "result.json").exists()
