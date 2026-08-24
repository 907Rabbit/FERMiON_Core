"""Six-stage FERMiON-HR training and evaluation curriculum."""

from __future__ import annotations

import math
import tempfile
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

import torch
from torch.nn import functional as F

from .adapters.llama_cpp import LlamaCppAdapter
from .adapters.unreal import UnrealAdapter
from .hr.config import HRConfig
from .hr.contracts import CandidateProgram, ProgramKind
from .hr.memory import EpisodicMemory, MemoryRecord
from .hr.reference_193 import FermionHR193, reference_inputs
from .hr.system import FermionHR
from .hr.trainer import HRTrainer, RoutingBatch
from .software.executor import ExecutionPolicy, GuardedExecutor, PolicyViolation
from .software.validators import JSONValidator


class StageStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class StageResult:
    stage: int
    name: str
    status: StageStatus
    metrics: dict[str, float]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CurriculumReport:
    stages: tuple[StageResult, ...]

    @property
    def passed(self) -> bool:
        return all(stage.status != StageStatus.FAILED for stage in self.stages)

    def to_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "stages": [asdict(stage) for stage in self.stages]}


@dataclass(frozen=True)
class CurriculumConfig:
    seed: int = 193
    stage1_steps: int = 250
    quick: bool = False


class CurriculumRunner:
    def __init__(self, config: CurriculumConfig | None = None,
                 llama: LlamaCppAdapter | None = None, unreal: UnrealAdapter | None = None):
        self.config = config or CurriculumConfig()
        self.llama = llama
        self.unreal = unreal
        self.model = FermionHR(HRConfig(seed=self.config.seed))
        self.trainer = HRTrainer(self.model)
        self._heldout: RoutingBatch | None = None

    def run(self) -> CurriculumReport:
        return CurriculumReport((self.stage0(), self.stage1(), self.stage2(), self.stage3(),
                                 self.stage4(), self.stage5(), self.stage6()))

    def stage0(self) -> StageResult:
        model = FermionHR193(seed=self.config.seed)
        x, psi, memory = reference_inputs()
        first, second = model(x, psi, memory), model(x, psi, memory)
        deterministic = torch.equal(first.logits, second.logits)
        finite = all(torch.isfinite(value).all() for value in (first.encoded, first.logits, first.success))
        loss = first.logits.sum(); loss.backward()
        gradient = model.W_e.grad[0, 0].item()
        epsilon = 1e-6
        with torch.no_grad():
            original = model.W_e[0, 0].item(); model.W_e[0, 0] = original + epsilon
            plus = model(x, psi, memory).logits.sum().item(); model.W_e[0, 0] = original - epsilon
            minus = model(x, psi, memory).logits.sum().item(); model.W_e[0, 0] = original
        numeric = (plus - minus) / (2 * epsilon)
        relative = abs(gradient - numeric) / max(1.0, abs(gradient), abs(numeric))
        passed = model.parameter_count == 193 and deterministic and finite and relative < 1e-4
        return StageResult(0, "mathematical_integrity", StageStatus.PASSED if passed else StageStatus.FAILED,
                           {"parameter_count": float(model.parameter_count),
                            "finite_difference_relative_error": relative,
                            "deterministic": float(deterministic), "finite": float(finite)})

    def _batch(self, seed: int, batch_size: int = 48) -> RoutingBatch:
        generator = torch.Generator().manual_seed(seed)
        observations = {}
        for name, dimension in self.model.config.modality_dims.items():
            observations[name] = torch.randn(batch_size, dimension, generator=generator)
        state = self.model.initial_state(batch_size)
        candidates = torch.randn(batch_size, 3, self.model.config.candidate_dim, generator=generator)
        # Controlled candidate family: quality, cost, and damage are independently observable.
        quality = torch.tensor([0.9, 0.2, 0.75]).expand(batch_size, -1)
        cost = torch.tensor([0.4, 0.1, 0.6]).expand(batch_size, -1)
        risk = torch.tensor([0.1, 0.05, 0.95]).expand(batch_size, -1)
        candidates[..., 0] = quality
        candidates[..., 1] = cost
        candidates[..., 2] = risk
        success = quality.clamp(0.01, 0.99)
        observed_energy = 1.0 - success + cost + 2.0 * risk
        best = observed_energy.argmin(dim=-1)
        return RoutingBatch(observations, state, candidates, success, observed_energy, best, cost, risk)

    def stage1(self) -> StageResult:
        train = self._batch(self.config.seed + 1, 64)
        heldout = self._batch(self.config.seed + 2, 48)
        self._heldout = heldout
        steps = 8 if self.config.quick else self.config.stage1_steps
        for _ in range(steps):
            self.trainer.train_step(train)
        self.model.eval()
        with torch.no_grad():
            decision = self.model(heldout.observations, heldout.state, heldout.candidates,
                                  heldout.external_cost, heldout.external_risk)
        accuracy = (decision.selected_index == heldout.best_indices).float().mean().item()
        brier = (decision.routing.success - heldout.success_targets).square().mean().item()
        destructive_rejection = (decision.selected_index != 2).float().mean().item()
        threshold = 0.80 if self.config.quick else 0.90
        passed = accuracy >= threshold and destructive_rejection >= 0.98
        return StageResult(1, "controlled_candidate_routing",
                           StageStatus.PASSED if passed else StageStatus.FAILED,
                           {"top1_accuracy": accuracy, "brier_score": brier,
                            "destructive_rejection": destructive_rejection},
                           ("Synthetic advancement gate is lower in quick mode.",) if self.config.quick else ())

    def stage2(self) -> StageResult:
        heldout = self._heldout or self._batch(self.config.seed + 2, 48)
        losses = {}
        self.model.eval()
        with torch.no_grad():
            encoded, _ = self.model.encoder(heldout.observations)
            for steps in (0, 1, 2, 3, 5):
                trace = self.model.core(heldout.state.psi, heldout.state.memory, encoded, steps)
                prediction = self.model.router(trace.final, heldout.state.psi, heldout.state.memory,
                                               encoded, heldout.candidates)
                losses[str(steps)] = F.binary_cross_entropy(prediction.success,
                                                            heldout.success_targets).item()
        stable = math.isfinite(losses["5"])
        # This is deliberately falsifiable; failure does not get hidden by later stages.
        passed = losses["3"] <= losses["0"] and stable
        return StageResult(2, "recursive_refinement", StageStatus.PASSED if passed else StageStatus.FAILED,
                           {f"loss_{step}_steps": value for step, value in losses.items()},
                           (() if passed else ("Three refinements did not beat zero-step inference.",)))

    def stage3(self) -> StageResult:
        with tempfile.TemporaryDirectory(prefix="fermion-memory-") as temporary:
            memory = EpisodicMemory(Path(temporary) / "memory.db")
            now = time.time()
            for index in range(12):
                key = (1.0, 0.0, index / 12)
                memory.write(MemoryRecord(key, (1.0,), {"version": "A"}, {"method": "X"},
                                          {"success": True}, {}, 1.0, 1.0, now - index), threshold=0.0)
            retrieved = memory.retrieve((1.0, 0.0, 0.5), limit=3, now=now)
            precision = sum(item.record.action.get("method") == "X" for item in retrieved) / len(retrieved)
            restart_count = len(memory); memory.close()
            reopened = EpisodicMemory(Path(temporary) / "memory.db")
            persisted = len(reopened) == restart_count; reopened.close()
        passed = precision == 1.0 and persisted
        return StageResult(3, "persistent_memory", StageStatus.PASSED if passed else StageStatus.FAILED,
                           {"retrieval_precision": precision, "records_after_restart": float(restart_count),
                            "restart_persistence": float(persisted)})

    def stage4(self) -> StageResult:
        with tempfile.TemporaryDirectory(prefix="fermion-execution-") as temporary:
            workspace = Path(temporary) / "project"; workspace.mkdir()
            executor = GuardedExecutor(workspace, ExecutionPolicy(timeout_seconds=2.0))
            validator = JSONValidator("result.json", ("sum", "mean"), {"sum": 6, "mean": 2})
            correct = CandidateProgram("correct", "import json\njson.dump({'sum':6,'mean':2},open('result.json','w'))",
                                       declared_artifacts=("result.json",))
            wrong = CandidateProgram("wrong", "import json\njson.dump({'sum':7,'mean':2},open('result.json','w'))",
                                     declared_artifacts=("result.json",))
            damaging = CandidateProgram("damage", "open('undeclared.txt','w').write('x')\nopen('result.json','w').write('{}')",
                                        declared_artifacts=("result.json",), estimated_risk=1.0)
            syntax = CandidateProgram("syntax", "this is not valid python", declared_artifacts=("result.json",))
            results = [executor.execute(candidate, validator) for candidate in (correct, wrong, damaging)]
            try:
                executor.execute(syntax, validator)
                syntax_found = False
            except PolicyViolation:
                syntax_found = True
        correct_success = results[0].validator.success == 1.0
        wrong_rejected = results[1].validator.success == 0.0
        damage_found = bool(results[2].undeclared_artifacts)
        passed = correct_success and wrong_rejected and damage_found and syntax_found
        return StageResult(4, "real_transactional_execution",
                           StageStatus.PASSED if passed else StageStatus.FAILED,
                           {"correct_success": float(correct_success), "wrong_rejected": float(wrong_rejected),
                            "undeclared_damage_detected": float(damage_found),
                            "syntax_failure_detected": float(syntax_found)})

    def stage5(self) -> StageResult:
        if self.llama is None:
            return StageResult(5, "local_llm_integration", StageStatus.SKIPPED, {},
                               ("Configure a llama.cpp server or CLI to run this external stage.",))
        try:
            proposals = self.llama.generate("create result.json with sum and mean", {}, 3)
            valid = len(proposals) >= 2 and all(proposal.provenance == "llama.cpp" for proposal in proposals)
            return StageResult(5, "local_llm_integration",
                               StageStatus.PASSED if valid else StageStatus.FAILED,
                               {"candidate_count": float(len(proposals))},
                               ("Execution outcomes, not llama.cpp self-rankings, remain the labels.",))
        except Exception as error:
            return StageResult(5, "local_llm_integration", StageStatus.FAILED, {},
                               (f"{type(error).__name__}: {error}",))

    def stage6(self) -> StageResult:
        if self.unreal is None:
            return StageResult(6, "unreal_engine_transfer", StageStatus.SKIPPED, {},
                               ("Configure UnrealEditor-Cmd and a .uproject to run this external stage.",))
        result = self.unreal.run_python("import unreal\nprint(unreal.EditorLevelLibrary.get_editor_world())")
        passed = result.return_code == 0 and not result.timed_out
        return StageResult(6, "unreal_engine_transfer",
                           StageStatus.PASSED if passed else StageStatus.FAILED,
                           {"command_success": float(passed), "timed_out": float(result.timed_out)})


def challenger_promotable(champion: dict[str, float], challenger: dict[str, float], epsilon: float = 0.0) -> bool:
    hard_gates = ("undeclared_modifications", "catastrophic_failures", "checkpoint_failures")
    if any(challenger.get(metric, 0.0) > champion.get(metric, 0.0) for metric in hard_gates):
        return False
    return challenger.get("aggregate_score", -math.inf) > champion.get("aggregate_score", -math.inf) + epsilon
