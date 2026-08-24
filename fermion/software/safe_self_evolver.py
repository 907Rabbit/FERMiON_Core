"""Bounded, auditable strategy evolution using only the Python standard library.

The controller and its policy are static. Only a generated arithmetic strategy
is eligible for replacement. This is an adaptive optimizer, not AGI or an
unrestricted self-modifying system.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Sequence

BASIS = ("constant", "linear", "quadratic", "sin", "cos", "tanh")
COEFFICIENT_LIMIT = 8.0
PREDICTION_LIMIT = 100.0
FORMAT_VERSION = 1
PROMPT = ("Build an auditable adaptive optimizer: keep controller, policy, tests, "
          "and audits immutable; evolve only typed-genome generated code; validate "
          "AST and subprocess behavior; select on frozen validation data; report held-"
          "out metrics only after selection; use provenance, atomic promotion and rollback.")


class EvolutionError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Genome:
    coefficients: tuple[float, ...]
    enabled: tuple[bool, ...]

    def __post_init__(self) -> None:
        if len(self.coefficients) != len(BASIS) or len(self.enabled) != len(BASIS):
            raise EvolutionError("genome does not match the fixed basis")
        if not any(self.enabled):
            raise EvolutionError("a genome must enable one basis")
        if any(not math.isfinite(x) or abs(x) > COEFFICIENT_LIMIT for x in self.coefficients):
            raise EvolutionError("coefficient is non-finite or out of range")

    def predict(self, x: float) -> float:
        values = (1.0, x, x * x, math.sin(x), math.cos(x), math.tanh(x))
        result = sum(c * v for c, v, enabled in zip(self.coefficients, values, self.enabled) if enabled)
        if not math.isfinite(result) or abs(result) > PREDICTION_LIMIT:
            raise EvolutionError("strategy output is non-finite or out of bounds")
        return result

    def as_dict(self) -> dict[str, object]:
        return {"basis": list(BASIS), "coefficients": list(self.coefficients), "enabled": list(self.enabled)}

    @classmethod
    def from_dict(cls, raw: object) -> "Genome":
        if not isinstance(raw, dict) or raw.get("basis") != list(BASIS):
            raise EvolutionError("genome basis contract mismatch")
        try:
            return cls(tuple(float(x) for x in raw["coefficients"]), tuple(bool(x) for x in raw["enabled"]))
        except (KeyError, TypeError, ValueError) as error:
            raise EvolutionError("malformed genome") from error


@dataclasses.dataclass(frozen=True)
class Example:
    x: float
    target: float
    weight: float = 1.0


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_json(path: Path, raw: object) -> None:
    atomic_write(path, json.dumps(raw, sort_keys=True, indent=2) + "\n")


def append_jsonl(path: Path, raw: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush(); os.fsync(stream.fileno())


def source_for(genome: Genome) -> str:
    expressions = ("1.0", "x", "x*x", "math.sin(x)", "math.cos(x)", "math.tanh(x)")
    terms = [f"({coefficient!r} * {expressions[index]})" for index, (coefficient, enabled)
             in enumerate(zip(genome.coefficients, genome.enabled)) if enabled]
    return ('"""Generated strategy; do not edit manually."""\nimport math\n\n'
            f"def predict(x):\n    return {' + '.join(terms)}\n")


ALLOWED_NODES = (ast.Module, ast.Expr, ast.Constant, ast.Import, ast.alias, ast.FunctionDef,
                 ast.arguments, ast.arg, ast.Return, ast.BinOp, ast.Add, ast.Mult,
                 ast.UnaryOp, ast.USub, ast.Name, ast.Load, ast.Call, ast.Attribute)


def validate_source(source: str) -> None:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as error:
        raise EvolutionError(f"syntax failure: {error}") from error
    imports = [node for node in tree.body if isinstance(node, ast.Import)]
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(imports) != 1 or [item.name for item in imports[0].names] != ["math"]:
        raise EvolutionError("only import math is permitted")
    if len(functions) != 1 or functions[0].name != "predict" or len(functions[0].args.args) != 1:
        raise EvolutionError("only def predict(x) is permitted")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise EvolutionError(f"disallowed AST node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in {"math", "x"}:
            raise EvolutionError(f"disallowed name: {node.id}")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or node.value.id != "math" or node.attr not in {"sin", "cos", "tanh"}:
                raise EvolutionError("disallowed attribute")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Attribute) or node.keywords or len(node.args) != 1):
            raise EvolutionError("only unary math calls are allowed")


def subprocess_probe(path: Path, xs: Sequence[float], timeout: float = 3.0) -> list[float]:
    program = ("import json,math,runpy,sys;mod=runpy.run_path(sys.argv[1]);"
               "ys=[mod['predict'](float(x)) for x in json.loads(sys.argv[2])];"
               "assert all(math.isfinite(y) and abs(y)<=100 for y in ys);print(json.dumps(ys))")
    environment = {"PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"}
    for key in ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP"):
        if key in os.environ: environment[key] = os.environ[key]
    try:
        result = subprocess.run([sys.executable, "-I", "-c", program, str(path), json.dumps(list(xs))],
                                capture_output=True, text=True, env=environment, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise EvolutionError("candidate subprocess timed out") from error
    if result.returncode != 0:
        raise EvolutionError(f"candidate subprocess failed: {result.stderr.strip()}")
    try:
        ys = [float(y) for y in json.loads(result.stdout)]
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise EvolutionError("candidate subprocess returned malformed output") from error
    if len(ys) != len(xs) or any(not math.isfinite(y) or abs(y) > PREDICTION_LIMIT for y in ys):
        raise EvolutionError("candidate subprocess output violates bounds")
    return ys


def target(x: float) -> float:
    return math.sin(x) + 0.3 * x * x - 0.2 * x


def dataset(seed: int, count: int) -> list[Example]:
    rng = random.Random(seed)
    return [Example(x, target(x)) for x in (rng.uniform(-2.5, 2.5) for _ in range(count))]


def weighted_mse(genome: Genome, rows: Iterable[Example]) -> float:
    numerator = denominator = 0.0
    for row in rows:
        if not all(math.isfinite(x) for x in (row.x, row.target, row.weight)) or row.weight <= 0:
            raise EvolutionError("invalid evaluation example")
        error = genome.predict(row.x) - row.target
        numerator += row.weight * error * error; denominator += row.weight
    if denominator <= 0 or not math.isfinite(numerator): raise EvolutionError("invalid metric")
    return numerator / denominator


def evolve_population(training: Sequence[Example], seed: int, generations: int, population: int, warm: Genome) -> tuple[Genome, list[dict[str, object]]]:
    if generations < 1 or population < 8: raise EvolutionError("invalid evolution budget")
    rng = random.Random(seed)
    def random_genome() -> Genome:
        enabled = [rng.random() < .65 for _ in BASIS]
        if not any(enabled): enabled[rng.randrange(len(enabled))] = True
        return Genome(tuple(rng.uniform(-1.5, 1.5) for _ in BASIS), tuple(enabled))
    def mutate(genome: Genome, sigma: float) -> Genome:
        coefficients, enabled = list(genome.coefficients), list(genome.enabled)
        for index in range(len(BASIS)):
            if rng.random() < .45: coefficients[index] = max(-COEFFICIENT_LIMIT, min(COEFFICIENT_LIMIT, coefficients[index] + rng.gauss(0, sigma)))
            if rng.random() < .06: enabled[index] = not enabled[index]
        if not any(enabled): enabled[rng.randrange(len(enabled))] = True
        return Genome(tuple(coefficients), tuple(enabled))
    members = [random_genome() for _ in range(population)]; members[0] = warm
    for index in range(1, min(8, population)): members[index] = mutate(warm, .35)
    score = lambda candidate: weighted_mse(candidate, training) + 1e-6 * sum(candidate.enabled)
    history: list[dict[str, object]] = []
    for generation in range(generations):
        ranked = sorted(members, key=score); best = ranked[0]
        history.append({"generation": generation, "training_mse": weighted_mse(best, training), "complexity": sum(best.enabled)})
        parents = ranked[:max(4, population // 5)]; members = parents[:2]
        sigma = max(.025, .5 * (1 - generation / max(1, generations - 1)))
        while len(members) < population:
            left, right = rng.choice(parents), rng.choice(parents)
            coefficients = tuple(a if rng.random() < .5 else b for a, b in zip(left.coefficients, right.coefficients))
            enabled = tuple(a if rng.random() < .5 else b for a, b in zip(left.enabled, right.enabled))
            if not any(enabled): enabled = tuple(index == 0 for index in range(len(BASIS)))
            members.append(mutate(Genome(coefficients, enabled), sigma))
    return min(members, key=score), history


class SafeSelfEvolver:
    def __init__(self, workspace: Path):
        self.root = workspace.resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.active = self.root / "active_strategy.py"; self.state_path = self.root / "state.json"
        self.audit = self.root / "audit.jsonl"; self.feedback_path = self.root / "feedback.jsonl"
        self.versions = self.root / "versions"; self.versions.mkdir(exist_ok=True)

    @staticmethod
    def baseline() -> Genome: return Genome((0.0,) * len(BASIS), (True,) + (False,) * (len(BASIS) - 1))

    def state(self) -> dict[str, object] | None:
        if not self.state_path.exists(): return None
        try: state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error: raise EvolutionError("malformed state") from error
        required = {"format_version", "active_version", "next_version", "versions", "active_genome", "active_sha256"}
        if not isinstance(state, dict) or state.get("format_version") != FORMAT_VERSION or not required.issubset(state): raise EvolutionError("state contract mismatch")
        if not self.active.is_file() or file_hash(self.active) != state["active_sha256"]: raise EvolutionError("active strategy hash mismatch")
        Genome.from_dict(state["active_genome"]); return state

    def active_genome(self) -> Genome:
        state = self.state(); return Genome.from_dict(state["active_genome"]) if state else self.baseline()

    def feedback(self) -> list[Example]:
        if not self.feedback_path.exists(): return []
        examples = []
        for number, line in enumerate(self.feedback_path.read_text(encoding="utf-8").splitlines(), 1):
            try: raw = json.loads(line); example = Example(float(raw["x"]), float(raw["target"]), float(raw["weight"]))
            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as error: raise EvolutionError(f"malformed feedback line {number}") from error
            if not all(math.isfinite(x) for x in (example.x, example.target, example.weight)) or example.weight <= 0: raise EvolutionError(f"invalid feedback line {number}")
            examples.append(example)
        return examples

    def record_feedback(self, x: float, target_value: float, weight: float) -> dict[str, object]:
        if not all(math.isfinite(v) for v in (x, target_value, weight)) or weight <= 0 or abs(x) > 20 or abs(target_value) > 100: raise EvolutionError("feedback violates range policy")
        record: dict[str, object] = {"event": "feedback", "time_ns": time.time_ns(), "x": x, "target": target_value, "weight": weight}
        append_jsonl(self.feedback_path, record); append_jsonl(self.audit, record); return record

    def promote(self, genome: Genome, validation: float, held_out: float, seed: int) -> dict[str, object]:
        candidate = self.root / "candidate_strategy.py"
        try:
            source = source_for(genome); validate_source(source); atomic_write(candidate, source)
            points = (-2.5, -1.0, 0.0, .75, 2.5)
            if any(abs(a - b) > 1e-12 for a, b in zip(subprocess_probe(candidate, points), [genome.predict(x) for x in points])): raise EvolutionError("typed genome/source mismatch")
            candidate_hash = file_hash(candidate); prior = self.state(); versions = list(prior["versions"]) if prior else []
            number = int(prior["next_version"]) if prior else 1; version = self.versions / f"strategy_v{number:04d}.py"
            if version.exists(): raise EvolutionError("immutable version path already exists")
            atomic_write(version, source); atomic_write(self.active, source)
            if file_hash(version) != candidate_hash or file_hash(self.active) != candidate_hash: raise EvolutionError("atomic promotion hash mismatch")
            entry: dict[str, object] = {"version": number, "path": str(version), "sha256": candidate_hash, "validation_mse": validation, "held_out_test_mse_report_only": held_out, "seed": seed, "genome": genome.as_dict()}
            versions.append(entry); atomic_json(self.state_path, {"format_version": FORMAT_VERSION, "active_version": number, "next_version": number + 1, "versions": versions, "active_genome": genome.as_dict(), "active_sha256": candidate_hash})
            append_jsonl(self.audit, {"event": "promote", "time_ns": time.time_ns(), **entry}); return entry
        finally: candidate.unlink(missing_ok=True)

    def evolve(self, seed: int, generations: int, population: int, minimum_improvement: float) -> dict[str, object]:
        if not 0 <= minimum_improvement < 1: raise EvolutionError("minimum improvement must lie in [0,1)")
        training, validation, held_out = dataset(1001, 160), dataset(2002, 80), dataset(3003, 80)
        active = self.active_genome(); before = weighted_mse(active, validation)
        candidate, history = evolve_population(training + self.feedback(), seed, generations, population, active)
        after = weighted_mse(candidate, validation); selected = after < before * (1 - minimum_improvement)
        result: dict[str, object] = {"seed": seed, "generations": generations, "population": population, "active_validation_mse": before, "candidate_validation_mse": after, "relative_validation_improvement": 1 - after / before if before else 0, "selected_from_validation_only": selected, "history": history, "candidate_genome": candidate.as_dict()}
        # This final data is accessed after the validation selection, never for ranking.
        result["held_out_test_mse_report_only"] = weighted_mse(candidate, held_out)
        if selected: result["promotion"] = self.promote(candidate, after, float(result["held_out_test_mse_report_only"]), seed)
        else: append_jsonl(self.audit, {"event": "reject", "time_ns": time.time_ns(), "seed": seed, "active_validation_mse": before, "candidate_validation_mse": after})
        return result

    def rollback(self) -> dict[str, object]:
        state = self.state()
        if not state: raise EvolutionError("no promoted strategy exists")
        current = int(state["active_version"]); previous = [entry for entry in state["versions"] if int(entry["version"]) < current]
        if not previous: raise EvolutionError("no preceding version exists")
        entry = previous[-1]; path = Path(str(entry["path"]))
        if not path.is_file() or file_hash(path) != entry["sha256"]: raise EvolutionError("rollback provenance mismatch")
        source = path.read_text(encoding="utf-8"); validate_source(source); atomic_write(self.active, source)
        state["active_version"] = entry["version"]; state["active_genome"] = entry["genome"]; state["active_sha256"] = file_hash(self.active); atomic_json(self.state_path, state)
        event: dict[str, object] = {"event": "rollback", "time_ns": time.time_ns(), "from_version": current, "to_version": entry["version"], "sha256": state["active_sha256"]}; append_jsonl(self.audit, event); return event

    def status(self) -> dict[str, object]:
        state = self.state(); return {"workspace": str(self.root), "initialized": bool(state), "active_version": state["active_version"] if state else 0, "active_sha256": state["active_sha256"] if state else None, "version_count": len(state["versions"]) if state else 0, "feedback_count": len(self.feedback()), "description": "auditable adaptive optimizer, not unrestricted self-modification"}


def run_self_tests() -> dict[str, object]:
    first = Genome((.1, -.2, .3, 1., 0., 0.), (True, True, True, True, False, False)); validate_source(source_for(first))
    try: validate_source("import os\ndef predict(x):\n return os.system('unsafe')\n")
    except EvolutionError: pass
    else: raise AssertionError("AST policy accepted unauthorized source")
    with tempfile.TemporaryDirectory(prefix="fermion_evolver_") as directory:
        root = Path(directory); probe = root / "strategy.py"; atomic_write(probe, source_for(first))
        observed = subprocess_probe(probe, (-1., 0., 1.)); expected = [first.predict(x) for x in (-1., 0., 1.)]
        if any(abs(actual - wanted) > 1e-12 for actual, wanted in zip(observed, expected)): raise AssertionError("generated source mismatch")
        evolver = SafeSelfEvolver(root / "runtime"); one = evolver.promote(first, 1., 1.1, 1)
        two = evolver.promote(Genome((.2, -.2, .3, 1., 0., 0.), first.enabled), .9, 1., 2)
        atomic_write(evolver.active, "tampered\n")
        try: evolver.status()
        except EvolutionError: pass
        else: raise AssertionError("hash enforcement failed")
        atomic_write(evolver.active, Path(str(two["path"])).read_text(encoding="utf-8"))
        if evolver.rollback()["to_version"] != one["version"]: raise AssertionError("rollback failed")
    return {"passed": True, "checks": ["AST rejection", "typed/source equivalence", "finite bounded subprocess", "atomic promotion", "SHA-256 provenance", "rollback"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--workspace", type=Path, default=Path("self_evolver_runtime")); commands = parser.add_subparsers(dest="command", required=True)
    for name in ("self-test", "status", "rollback", "prompt"): commands.add_parser(name)
    feedback = commands.add_parser("feedback"); feedback.add_argument("--x", type=float, required=True); feedback.add_argument("--target", type=float, required=True); feedback.add_argument("--weight", type=float, default=2.)
    for name in ("demo", "evolve"):
        item = commands.add_parser(name); item.add_argument("--seed", type=int, default=42); item.add_argument("--generations", type=int, default=60); item.add_argument("--population", type=int, default=80); item.add_argument("--minimum-improvement", type=float, default=.001)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prompt": print(PROMPT); return 0
        if args.command == "self-test": print(json.dumps(run_self_tests(), indent=2)); return 0
        evolver = SafeSelfEvolver(args.workspace)
        if args.command == "feedback": output = evolver.record_feedback(args.x, args.target, args.weight)
        elif args.command == "status": output = evolver.status()
        elif args.command == "rollback": output = evolver.rollback()
        else:
            if args.command == "demo": run_self_tests()
            output = evolver.evolve(args.seed, args.generations, args.population, args.minimum_improvement)
        print(json.dumps(output, indent=2)); return 0
    except (EvolutionError, OSError, json.JSONDecodeError) as error:
        print(f"FATAL: {error}", file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
