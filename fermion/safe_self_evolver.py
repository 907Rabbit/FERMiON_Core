#!/usr/bin/env python3
"""FERMiON Safe Self-Evolver.

Four evolution layers:
1. Self-modification: rewrites a generated strategy module, never this controller.
2. Interaction: stores user feedback as weighted learning examples.
3. Genetic evolution: mutates/crosses strategy structures and coefficients.
4. Falsification: validates syntax/behavior, requires held-out improvement,
   hashes every promoted version, and supports rollback.

The demonstration learns a bounded one-dimensional regression problem. It is a
small, auditable evolution kernel—not a claim of general intelligence.
Standard-library only; Python 3.10+ recommended.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys
import tempfile
import time
from typing import Iterable, Sequence


AI_BUILD_PROMPT = r"""
Build a constrained self-evolving Python system with four layers:

1. Self-modifying code
   - Keep the controller, safety rules, tests, and audit system immutable.
   - Permit modification only inside a generated strategy module.
   - Generate strategy source from a typed genome; never execute arbitrary
     model-written text.
   - Parse every candidate with Python AST and accept only a small explicit
     syntax/name/function whitelist.

2. Evolution through interaction
   - Accept explicit user/environment feedback as timestamped learning examples.
   - Preserve the examples in append-only JSONL with provenance.
   - Use feedback in later evolution while retaining a validation split so that
     adaptation is measured rather than assumed.

3. Genetic/AI evolution
   - Maintain a population of strategy genomes.
   - Use deterministic seeded selection, elitism, crossover, mutation, and a
     complexity penalty.
   - Evaluate candidates on frozen training and validation data.
   - Do not tune on the final held-out test set.

4. Falsification, provenance, and rollback
   - A candidate may be promoted only if it is finite, bounded, passes property
     tests, and improves the frozen validation metric by a predeclared margin.
   - Write promotions atomically, version every strategy, calculate SHA-256,
     append an audit event, and retain the previous version for rollback.
   - Run generated code in an isolated subprocess with a timeout.
   - Hard-fail on malformed state, non-finite values, hash mismatches, missing
     artifacts, or failed tests. Never silently drop failures.

Deliver a runnable standard-library Python program with CLI commands for
self-test, demo/evolve, feedback, status, rollback, and printing this prompt.
Include deterministic tests showing AST rejection, generated-code equivalence,
promotion, provenance, and rollback. Clearly state that the program is an
auditable adaptive optimizer, not evidence of AGI or unrestricted autonomy.
""".strip()


BASIS_NAMES = ("1", "x", "x2", "sin", "cos", "tanh")
COEFF_LIMIT = 8.0
PREDICTION_LIMIT = 100.0
FORMAT_VERSION = 1
ENGINE_ID = "fermion.safe_self_evolver.v1"


class EvolutionError(RuntimeError):
    """Hard failure in an evolution or provenance invariant."""


@dataclasses.dataclass(frozen=True)
class Genome:
    coefficients: tuple[float, ...]
    enabled: tuple[bool, ...]

    def __post_init__(self) -> None:
        if len(self.coefficients) != len(BASIS_NAMES):
            raise EvolutionError("wrong coefficient count")
        if len(self.enabled) != len(BASIS_NAMES):
            raise EvolutionError("wrong structure-mask count")
        if not any(self.enabled):
            raise EvolutionError("a strategy must enable at least one basis")
        if any(not math.isfinite(c) or abs(c) > COEFF_LIMIT for c in self.coefficients):
            raise EvolutionError("invalid or out-of-range coefficient")

    def predict(self, x: float) -> float:
        values = (1.0, x, x * x, math.sin(x), math.cos(x), math.tanh(x))
        value = sum(c * v for c, v, on in zip(self.coefficients, values, self.enabled) if on)
        if not math.isfinite(value) or abs(value) > PREDICTION_LIMIT:
            raise EvolutionError("candidate produced an invalid prediction")
        return value

    def to_json(self) -> dict:
        return {
            "coefficients": list(self.coefficients),
            "enabled": list(self.enabled),
            "basis": list(BASIS_NAMES),
        }

    @staticmethod
    def from_json(obj: dict) -> "Genome":
        if obj.get("basis") != list(BASIS_NAMES):
            raise EvolutionError("genome basis contract mismatch")
        return Genome(
            tuple(float(v) for v in obj["coefficients"]),
            tuple(bool(v) for v in obj["enabled"]),
        )


@dataclasses.dataclass(frozen=True)
class Example:
    x: float
    target: float
    weight: float = 1.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, obj: object) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def basis_expression(index: int) -> str:
    return ("1.0", "x", "x*x", "math.sin(x)", "math.cos(x)", "math.tanh(x)")[index]


def source_for_genome(genome: Genome) -> str:
    terms = [
        f"({coefficient!r} * {basis_expression(index)})"
        for index, (coefficient, enabled) in enumerate(zip(genome.coefficients, genome.enabled))
        if enabled
    ]
    expression = " + ".join(terms) if terms else "0.0"
    return (
        '"""Auto-generated strategy. Do not edit manually."""\n'
        "import math\n\n"
        "def predict(x):\n"
        f"    return {expression}\n"
    )


ALLOWED_AST_NODES = (
    ast.Module,
    ast.Expr,
    ast.Constant,
    ast.Import,
    ast.alias,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.BinOp,
    ast.Add,
    ast.Mult,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.Attribute,
    ast.UnaryOp,
    ast.USub,
)


def validate_strategy_source(source: str) -> None:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise EvolutionError(f"candidate syntax failure: {exc}") from exc
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    imports = [node for node in tree.body if isinstance(node, ast.Import)]
    if len(functions) != 1 or functions[0].name != "predict":
        raise EvolutionError("candidate must contain exactly one predict function")
    if len(imports) != 1 or [a.name for a in imports[0].names] != ["math"]:
        raise EvolutionError("candidate may import only math")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise EvolutionError(f"disallowed AST node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in {"x", "math"}:
            raise EvolutionError(f"disallowed name: {node.id}")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or node.value.id != "math":
                raise EvolutionError("only math attributes are allowed")
            if node.attr not in {"sin", "cos", "tanh"}:
                raise EvolutionError(f"disallowed math function: {node.attr}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute):
                raise EvolutionError("only whitelisted math calls are allowed")
            if node.keywords or len(node.args) != 1:
                raise EvolutionError("math calls require exactly one positional argument")


def subprocess_probe(path: Path, points: Sequence[float], timeout: float = 3.0) -> list[float]:
    probe = (
        "import json,math,runpy,sys;"
        "m=runpy.run_path(sys.argv[1]);"
        "xs=json.loads(sys.argv[2]);"
        "ys=[m['predict'](float(x)) for x in xs];"
        "assert all(math.isfinite(y) and abs(y)<=100.0 for y in ys);"
        "print(json.dumps(ys,separators=(',',':')))"
    )
    # Python on Windows may require SystemRoot/WINDIR for DLL and side-by-side
    # assembly resolution. Preserve only the small platform allowlist needed to
    # start the interpreter; -I still isolates Python imports and user packages.
    probe_environment = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
    }
    for key in ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP"):
        if key in os.environ:
            probe_environment[key] = os.environ[key]
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(path), json.dumps(list(points))],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=probe_environment,
    )
    if result.returncode != 0:
        raise EvolutionError(f"candidate subprocess test failed: {result.stderr.strip()}")
    values = json.loads(result.stdout)
    if len(values) != len(points):
        raise EvolutionError("candidate subprocess returned the wrong output count")
    return [float(value) for value in values]


def target_function(x: float) -> float:
    return math.sin(x) + 0.3 * x * x - 0.2 * x


def make_dataset(seed: int, count: int) -> list[Example]:
    rng = random.Random(seed)
    return [Example(x := rng.uniform(-2.5, 2.5), target_function(x)) for _ in range(count)]


def weighted_mse(genome: Genome, examples: Iterable[Example]) -> float:
    numerator = 0.0
    denominator = 0.0
    for example in examples:
        error = genome.predict(example.x) - example.target
        numerator += example.weight * error * error
        denominator += example.weight
    if denominator <= 0.0:
        raise EvolutionError("empty or invalid evaluation set")
    value = numerator / denominator
    if not math.isfinite(value):
        raise EvolutionError("non-finite metric")
    return value


def complexity(genome: Genome) -> int:
    return sum(genome.enabled)


def random_genome(rng: random.Random) -> Genome:
    enabled = [rng.random() < 0.65 for _ in BASIS_NAMES]
    if not any(enabled):
        enabled[rng.randrange(len(enabled))] = True
    coefficients = [rng.uniform(-1.5, 1.5) for _ in BASIS_NAMES]
    return Genome(tuple(coefficients), tuple(enabled))


def clamp_coefficient(value: float) -> float:
    return max(-COEFF_LIMIT, min(COEFF_LIMIT, value))


def mutate(genome: Genome, rng: random.Random, sigma: float) -> Genome:
    coefficients = list(genome.coefficients)
    enabled = list(genome.enabled)
    for index in range(len(coefficients)):
        if rng.random() < 0.45:
            coefficients[index] = clamp_coefficient(coefficients[index] + rng.gauss(0.0, sigma))
        if rng.random() < 0.06:
            enabled[index] = not enabled[index]
    if not any(enabled):
        enabled[rng.randrange(len(enabled))] = True
    return Genome(tuple(coefficients), tuple(enabled))


def crossover(first: Genome, second: Genome, rng: random.Random) -> Genome:
    coefficients = tuple(a if rng.random() < 0.5 else b for a, b in zip(first.coefficients, second.coefficients))
    enabled = tuple(a if rng.random() < 0.5 else b for a, b in zip(first.enabled, second.enabled))
    if not any(enabled):
        selected_index = rng.randrange(len(enabled))
        enabled = tuple(index == selected_index for index in range(len(enabled)))
    return Genome(coefficients, enabled)


def evolve_population(
    training: Sequence[Example],
    seed: int,
    generations: int,
    population_size: int,
    warm_start: Genome | None,
) -> tuple[Genome, list[dict]]:
    if generations < 1 or population_size < 8:
        raise EvolutionError("evolution budget is too small")
    rng = random.Random(seed)
    population = [random_genome(rng) for _ in range(population_size)]
    if warm_start is not None:
        population[0] = warm_start
        for index in range(1, min(8, population_size)):
            population[index] = mutate(warm_start, rng, sigma=0.35)
    history: list[dict] = []
    for generation in range(generations):
        sigma = max(0.025, 0.5 * (1.0 - generation / max(1, generations - 1)))
        fitness = {
            genome: weighted_mse(genome, training) + 1e-6 * complexity(genome)
            for genome in set(population)
        }
        ranked = sorted(population, key=fitness.__getitem__)
        best = ranked[0]
        history.append(
            {
                "generation": generation,
                "training_mse": weighted_mse(best, training),
                "complexity": complexity(best),
            }
        )
        parent_count = max(4, population_size // 5)
        parents = ranked[:parent_count]
        next_population = parents[:2]
        while len(next_population) < population_size:
            child = crossover(rng.choice(parents), rng.choice(parents), rng)
            next_population.append(mutate(child, rng, sigma=sigma))
        population = next_population
    final_fitness = {
        genome: weighted_mse(genome, training) + 1e-6 * complexity(genome)
        for genome in set(population)
    }
    return min(population, key=final_fitness.__getitem__), history


class SafeSelfEvolver:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.active_path = self.workspace / "active_strategy.py"
        self.state_path = self.workspace / "state.json"
        self.audit_path = self.workspace / "audit.jsonl"
        self.feedback_path = self.workspace / "interaction_memory.jsonl"
        self.versions_path = self.workspace / "versions"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.versions_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def zero_genome() -> Genome:
        return Genome((0.0,) * len(BASIS_NAMES), (True, False, False, False, False, False))

    def _read_state(self) -> dict | None:
        if not self.state_path.exists():
            return None
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("format_version") != FORMAT_VERSION:
            raise EvolutionError("state format mismatch")
        required = {"format_version", "active_version", "versions", "active_genome", "active_sha256"}
        if not required.issubset(state):
            raise EvolutionError("state is incomplete")
        if not self.active_path.is_file():
            raise EvolutionError("active strategy is missing")
        if sha256_file(self.active_path) != state["active_sha256"]:
            raise EvolutionError("active strategy hash mismatch")
        versions = state["versions"]
        if not isinstance(versions, list) or any(not isinstance(item, dict) for item in versions):
            raise EvolutionError("state versions are malformed")
        active_version = state["active_version"]
        if type(active_version) is not int or active_version < 1:
            raise EvolutionError("active version is invalid")
        matching = [item for item in versions if item.get("version") == active_version]
        if len(matching) != 1:
            raise EvolutionError("active version does not match exactly one version entry")
        active_entry = matching[0]
        if active_entry.get("sha256") != state["active_sha256"]:
            raise EvolutionError("active version hash does not match state")
        if active_entry.get("genome") != state["active_genome"]:
            raise EvolutionError("active version genome does not match state")
        return state

    def active_genome(self) -> Genome:
        state = self._read_state()
        return Genome.from_json(state["active_genome"]) if state else self.zero_genome()

    def feedback_examples(self) -> list[Example]:
        if not self.feedback_path.exists():
            return []
        examples: list[Example] = []
        for line_number, line in enumerate(self.feedback_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                example = Example(float(record["x"]), float(record["target"]), float(record["weight"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise EvolutionError(f"invalid feedback at line {line_number}") from exc
            if not all(math.isfinite(v) for v in (example.x, example.target, example.weight)):
                raise EvolutionError(f"non-finite feedback at line {line_number}")
            if example.weight <= 0.0 or abs(example.x) > 20.0 or abs(example.target) > 100.0:
                raise EvolutionError(f"out-of-range feedback at line {line_number}")
            examples.append(example)
        return examples

    def record_feedback(self, x: float, target: float, weight: float) -> dict:
        if not all(math.isfinite(v) for v in (x, target, weight)):
            raise EvolutionError("feedback must be finite")
        if weight <= 0.0 or abs(x) > 20.0 or abs(target) > 100.0:
            raise EvolutionError("feedback is outside the allowed range")
        record = {"time_ns": time.time_ns(), "x": x, "target": target, "weight": weight}
        append_jsonl(self.feedback_path, record)
        return record

    def _validate_generated_equivalence(self, genome: Genome, source_path: Path) -> None:
        points = (-2.5, -1.0, 0.0, 0.75, 2.5)
        generated = subprocess_probe(source_path, points)
        expected = [genome.predict(x) for x in points]
        if any(abs(a - b) > 1e-12 for a, b in zip(generated, expected)):
            raise EvolutionError("generated source does not match its genome")

    def promote(self, genome: Genome, validation_mse: float, test_mse: float, seed: int,
                dataset_seeds: dict[str, int] | None = None) -> dict:
        source = source_for_genome(genome)
        validate_strategy_source(source)
        candidate_path = self.workspace / "candidate_strategy.py"
        atomic_write_text(candidate_path, source)
        try:
            self._validate_generated_equivalence(genome, candidate_path)
            state = self._read_state()
            versions = list(state["versions"]) if state else []
            version_number = len(versions) + 1
            version_path = self.versions_path / f"strategy_v{version_number:04d}.py"
            if version_path.exists():
                raise EvolutionError("version path already exists")
            atomic_write_text(version_path, source)
            version_sha = sha256_file(version_path)
            atomic_write_text(self.active_path, source)
            active_sha = sha256_file(self.active_path)
            if active_sha != version_sha:
                raise EvolutionError("atomic promotion changed candidate bytes")
            entry = {
                "version": version_number,
                "path": str(version_path),
                "sha256": version_sha,
                "validation_mse": validation_mse,
                "test_mse_report_only": test_mse,
                "seed": seed,
                "dataset_seeds": dict(dataset_seeds) if dataset_seeds is not None else None,
                "genome": genome.to_json(),
            }
            versions.append(entry)
            new_state = {
                "format_version": FORMAT_VERSION,
                "active_version": version_number,
                "versions": versions,
                "active_genome": genome.to_json(),
                "active_sha256": active_sha,
            }
            atomic_write_json(self.state_path, new_state)
            append_jsonl(
                self.audit_path,
                {"event": "promote", "time_ns": time.time_ns(), **entry},
            )
            return entry
        finally:
            candidate_path.unlink(missing_ok=True)

    def rollback(self) -> dict:
        state = self._read_state()
        if state is None or len(state["versions"]) < 2:
            raise EvolutionError("no previous promoted version is available")
        current = int(state["active_version"])
        current_indices = [
            index for index, item in enumerate(state["versions"])
            if item.get("version") == current
        ]
        if len(current_indices) != 1 or current_indices[0] == 0:
            raise EvolutionError("no previous promoted version is available")
        previous_entry = state["versions"][current_indices[0] - 1]
        previous_path = Path(previous_entry["path"])
        if not previous_path.is_file() or sha256_file(previous_path) != previous_entry["sha256"]:
            raise EvolutionError("rollback version failed provenance verification")
        source = previous_path.read_text(encoding="utf-8")
        validate_strategy_source(source)
        atomic_write_text(self.active_path, source)
        restored_sha = sha256_file(self.active_path)
        if restored_sha != previous_entry["sha256"]:
            raise EvolutionError("restored active file hash mismatch")
        state["active_version"] = previous_entry["version"]
        state["active_genome"] = previous_entry["genome"]
        state["active_sha256"] = restored_sha
        atomic_write_json(self.state_path, state)
        event = {
            "event": "rollback",
            "time_ns": time.time_ns(),
            "from_version": current,
            "to_version": previous_entry["version"],
            "sha256": restored_sha,
        }
        append_jsonl(self.audit_path, event)
        return event

    def evolve(
        self,
        seed: int,
        generations: int,
        population_size: int,
        minimum_improvement: float,
        train_seed: int = 1001,
        val_seed: int = 2002,
        test_seed: int = 3003,
    ) -> dict:
        if any(type(value) is not int for value in (seed, train_seed, val_seed, test_seed)):
            raise EvolutionError("evolution and dataset seeds must be integers")
        if len({train_seed, val_seed, test_seed}) != 3:
            raise EvolutionError("training, validation, and test seeds must be distinct")
        if type(generations) is not int or generations < 1:
            raise EvolutionError("generations must be a positive integer")
        if type(population_size) is not int or population_size < 8:
            raise EvolutionError("population size must be an integer of at least 8")
        if not isinstance(minimum_improvement, (int, float)) or isinstance(minimum_improvement, bool):
            raise EvolutionError("minimum improvement must be numeric")
        minimum_improvement = float(minimum_improvement)
        if not math.isfinite(minimum_improvement) or not 0.0 <= minimum_improvement < 1.0:
            raise EvolutionError("minimum improvement must lie in [0, 1)")
        training = make_dataset(seed=train_seed, count=160)
        validation = make_dataset(seed=val_seed, count=80)
        test = make_dataset(seed=test_seed, count=80)
        feedback = self.feedback_examples()
        # Feedback changes the optimization objective but does not alter the frozen
        # synthetic validation/test sets. It therefore cannot manufacture a pass.
        training = training + feedback
        active = self.active_genome()
        active_validation = weighted_mse(active, validation)
        candidate, history = evolve_population(training, seed, generations, population_size, active)
        candidate_validation = weighted_mse(candidate, validation)
        required = active_validation * (1.0 - minimum_improvement)
        promoted = candidate_validation < required
        candidate_test = weighted_mse(candidate, test)
        result = {
            "seed": seed,
            "dataset_seeds": {
                "training": train_seed,
                "validation": val_seed,
                "test": test_seed,
            },
            "generations": generations,
            "population_size": population_size,
            "feedback_examples": len(feedback),
            "active_validation_mse": active_validation,
            "candidate_validation_mse": candidate_validation,
            "relative_validation_improvement": 1.0 - candidate_validation / active_validation
            if active_validation > 0.0
            else 0.0,
            "candidate_test_mse_report_only": candidate_test,
            "promoted": promoted,
            "history": history,
            "candidate_genome": candidate.to_json(),
        }
        if promoted:
            result["promotion"] = self.promote(
                candidate, candidate_validation, candidate_test, seed,
                dataset_seeds=result["dataset_seeds"],
            )
        else:
            append_jsonl(
                self.audit_path,
                {
                    "event": "reject",
                    "time_ns": time.time_ns(),
                    "seed": seed,
                    "dataset_seeds": result["dataset_seeds"],
                    "active_validation_mse": active_validation,
                    "candidate_validation_mse": candidate_validation,
                    "candidate_genome": candidate.to_json(),
                },
            )
        return result

    def status(self) -> dict:
        state = self._read_state()
        return {
            "engine_id": ENGINE_ID,
            "workspace": str(self.workspace),
            "initialized": state is not None,
            "active_version": state["active_version"] if state else 0,
            "active_sha256": state["active_sha256"] if state else None,
            "version_count": len(state["versions"]) if state else 0,
            "feedback_count": len(self.feedback_examples()),
        }

    def list_versions(self) -> list[dict]:
        """Return promoted version metadata after verifying active state provenance."""
        state = self._read_state()
        return list(state["versions"]) if state else []


def run_self_tests() -> dict:
    genome = Genome((0.1, -0.2, 0.3, 1.0, 0.0, 0.0), (True, True, True, True, False, False))
    source = source_for_genome(genome)
    validate_strategy_source(source)
    rejected_malicious = False
    try:
        validate_strategy_source("import os\ndef predict(x):\n    return os.system('echo unsafe')\n")
    except EvolutionError:
        rejected_malicious = True
    if not rejected_malicious:
        raise AssertionError("AST gate accepted malicious source")
    with tempfile.TemporaryDirectory(prefix="safe_self_evolver_test_") as directory:
        root = Path(directory)
        candidate = root / "strategy.py"
        atomic_write_text(candidate, source)
        values = subprocess_probe(candidate, (-1.0, 0.0, 1.0))
        expected = [genome.predict(x) for x in (-1.0, 0.0, 1.0)]
        if any(abs(a - b) > 1e-12 for a, b in zip(values, expected)):
            raise AssertionError("generated strategy mismatch")
        evolver = SafeSelfEvolver(root / "runtime")
        first = evolver.promote(genome, validation_mse=1.0, test_mse=1.1, seed=1)
        second_genome = Genome((0.2, -0.2, 0.3, 1.0, 0.0, 0.0), (True, True, True, True, False, False))
        second = evolver.promote(second_genome, validation_mse=0.9, test_mse=1.0, seed=2)
        rollback = evolver.rollback()
        status = evolver.status()
        if status["active_version"] != first["version"]:
            raise AssertionError("rollback failed")
        if second["sha256"] == first["sha256"]:
            raise AssertionError("self-modification did not change source")
        if rollback["to_version"] != first["version"]:
            raise AssertionError("rollback audit mismatch")
    return {
        "passed": True,
        "checks": [
            "AST whitelist rejects malicious source",
            "generated source equals typed genome",
            "subprocess probe is finite and bounded",
            "atomic promotion changes strategy bytes",
            "SHA-256 provenance is enforced",
            "rollback restores the previous version",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("self_evolver_runtime"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    evolve_parser = subparsers.add_parser("evolve", help="run one measured evolution cycle")
    evolve_parser.add_argument("--seed", type=int, default=42)
    evolve_parser.add_argument("--generations", type=int, default=60)
    evolve_parser.add_argument("--population", type=int, default=80)
    evolve_parser.add_argument("--minimum-improvement", type=float, default=0.001)
    evolve_parser.add_argument("--train-seed", type=int, default=1001)
    evolve_parser.add_argument("--val-seed", type=int, default=2002)
    evolve_parser.add_argument("--test-seed", type=int, default=3003)

    demo_parser = subparsers.add_parser("demo", help="run tests and one evolution cycle")
    demo_parser.add_argument("--seed", type=int, default=42)
    demo_parser.add_argument("--generations", type=int, default=60)
    demo_parser.add_argument("--population", type=int, default=80)
    demo_parser.add_argument("--train-seed", type=int, default=1001)
    demo_parser.add_argument("--val-seed", type=int, default=2002)
    demo_parser.add_argument("--test-seed", type=int, default=3003)

    feedback_parser = subparsers.add_parser("feedback", help="record a weighted interaction example")
    feedback_parser.add_argument("--x", type=float, required=True)
    feedback_parser.add_argument("--target", type=float, required=True)
    feedback_parser.add_argument("--weight", type=float, default=2.0)

    subparsers.add_parser("status", help="verify and display current state")
    subparsers.add_parser("rollback", help="restore the previous promoted strategy")
    subparsers.add_parser("versions", help="list all promoted versions")
    subparsers.add_parser("self-test", help="run deterministic safety/provenance tests")
    subparsers.add_parser("prompt", help="print the implementation prompt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prompt":
            print(AI_BUILD_PROMPT)
            return 0
        if args.command == "self-test":
            print(json.dumps(run_self_tests(), indent=2))
            return 0
        evolver = SafeSelfEvolver(args.workspace)
        if args.command == "feedback":
            print(json.dumps(evolver.record_feedback(args.x, args.target, args.weight), indent=2))
        elif args.command == "status":
            print(json.dumps(evolver.status(), indent=2))
        elif args.command == "rollback":
            print(json.dumps(evolver.rollback(), indent=2))
        elif args.command == "versions":
            print(json.dumps(evolver.list_versions(), indent=2))
        elif args.command == "evolve":
            result = evolver.evolve(
                args.seed, args.generations, args.population, args.minimum_improvement,
                args.train_seed, args.val_seed, args.test_seed,
            )
            print(json.dumps(result, indent=2))
        elif args.command == "demo":
            tests = run_self_tests()
            result = evolver.evolve(
                args.seed, args.generations, args.population, minimum_improvement=0.001,
                train_seed=args.train_seed, val_seed=args.val_seed, test_seed=args.test_seed,
            )
            print(json.dumps({"self_tests": tests, "evolution": result, "status": evolver.status()}, indent=2))
        else:
            raise EvolutionError(f"unknown command: {args.command}")
        return 0
    except (EvolutionError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
