import argparse
import ast
import hashlib
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

WRITER_PATH = Path(__file__).resolve()
PROJECT_ROOT = WRITER_PATH.parents[3]
if PROJECT_ROOT != Path(r"G:\MyAIproject"):
    raise RuntimeError("unexpected project root")

OUTPUT_DIR = PROJECT_ROOT / "artifacts/cp10_p0_10_oracle_a"
ATTEMPTS_DIR = OUTPUT_DIR / "attempts"
EXPECTED_RELATIVE_TARGETS = frozenset(
    {
        "artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1a_source_manifest.json",
        "artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1a_case_coverage.json",
        "artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1a_test_manifest.json",
        "artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1a_readiness_audit.json",
        "artifacts/cp10_p0_10_oracle_a/attempts/attempt_032_manifest.json",
    }
)
ORDERED_TARGETS = (
    OUTPUT_DIR / "r2a2a2s1td1a_source_manifest.json",
    OUTPUT_DIR / "r2a2a2s1td1a_case_coverage.json",
    OUTPUT_DIR / "r2a2a2s1td1a_test_manifest.json",
    OUTPUT_DIR / "r2a2a2s1td1a_readiness_audit.json",
    ATTEMPTS_DIR / "attempt_032_manifest.json",
)
RECEIPT_SHA256 = "482D3EA675350BA359E66B61D381D0CA929CA7A2E02B56F5D07848C763506540"
OUTPUT_CONTRACT_SHA256 = "9C7A6F8A1100C39ECDFB2F94EFEADD9CCF8AAA43C3C8A5463F1712E474A62C03"
TARGET_24_SHA256 = "F1C34EE79719ED7809CF074DFDA3830C01CB54DFBD6D3D3DF1BE8C719874458C"
TARGET_25_SHA256 = "E34589D052A42DFFD8B9A5EA7D1EAB89E487EB1168A885116407C46002078639"
PHASE1_READINESS_SHA256 = "6280D70960AC5A871992FB43F4BD6628A755399D6BEB45AF9787B13895ACC75D"
ATTEMPT_025_SHA256 = "24E0B31E61E5C04F95EF55A834C3AB9DCC957B0886AB63CF9AD0EF1219F62246"
RUNNER_SHA256 = "086ECEB5EA87FCB4AF1EABB348074270F5F2193D2C078A681D32A8234DB41A1D"
RUNNER_BYTE_COUNT = 28607
HISTORICAL_TEST_INTERPRETER = r"G:\MyAIproject\.venv\Scripts\python.exe"
CURRENT_WRITER_INTERPRETER = r"C:\Users\antho\AppData\Local\Programs\Python\Python312\python.exe"
CURRENT_WRITER_PYTHON_VERSION = "3.12.10"


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path):
    return sha256_bytes(path.read_bytes())


def strict_parse(value):
    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    def reject_constant(value_text):
        raise ValueError(f"non-finite JSON constant: {value_text}")

    return json.loads(value.decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=reject_constant)


def relative_path(path):
    return path.relative_to(PROJECT_ROOT).as_posix()


def file_record(path):
    data = path.read_bytes()
    return {"path": relative_path(path), "sha256": sha256_bytes(data), "byte_count": len(data)}


def require_hash(path, expected):
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {relative_path(path)}: expected={expected}, actual={actual}")


def assert_exact_targets(items):
    actual_paths = [relative_path(path) for path, _ in items]
    actual_set = frozenset(actual_paths)
    if len(items) != 5 or len(actual_paths) != len(actual_set):
        raise RuntimeError("evidence output target count or uniqueness mismatch")
    if actual_set != EXPECTED_RELATIVE_TARGETS:
        missing = sorted(EXPECTED_RELATIVE_TARGETS - actual_set)
        extra = sorted(actual_set - EXPECTED_RELATIVE_TARGETS)
        raise RuntimeError(f"evidence output target mismatch: missing={missing}, extra={extra}")
    if tuple(path for path, _ in items) != ORDERED_TARGETS:
        raise RuntimeError("evidence output acyclic order mismatch")


class StaticCoverageError(RuntimeError):
    pass


def assignment_value(tree, name):
    matches = [
        node.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in ([*node.targets] if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name) and target.id == name
    ]
    if len(matches) != 1:
        raise StaticCoverageError(f"expected one assignment for {name}, found {len(matches)}")
    return matches[0]


def restricted_literal(node, constants):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = []
        for element in node.elts:
            if isinstance(element, ast.Starred):
                expanded = restricted_literal(element.value, constants)
                if not isinstance(expanded, (list, tuple, set, frozenset)):
                    raise StaticCoverageError(f"non-sequence starred literal: {ast.dump(element)}")
                values.extend(expanded)
            else:
                values.append(restricted_literal(element, constants))
        if isinstance(node, ast.List):
            return values
        if isinstance(node, ast.Tuple):
            return tuple(values)
        return set(values)
    if isinstance(node, ast.Dict):
        return {
            restricted_literal(key, constants): restricted_literal(value, constants)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = restricted_literal(node.left, constants)
        right = restricted_literal(node.right, constants)
        if not isinstance(left, (str, list, tuple)) or type(left) is not type(right):
            raise StaticCoverageError(f"unsupported literal concatenation: {ast.dump(node)}")
        return left + right
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) == 1
        and not node.keywords
    ):
        return frozenset(restricted_literal(node.args[0], constants))
    raise StaticCoverageError(f"unsupported literal AST: {ast.dump(node, include_attributes=False)}")


def static_production_targets(runner_tree):
    constants = {}
    for name in ("PRODUCTION_LAUNCH_RECORD_FILENAME", "PRODUCTION_ROOT_TARGETS", "RUNS"):
        constants[name] = restricted_literal(assignment_value(runner_tree, name), constants)

    generator_call = assignment_value(runner_tree, "PRODUCTION_RUN_TARGETS")
    if not (
        isinstance(generator_call, ast.Call)
        and isinstance(generator_call.func, ast.Name)
        and generator_call.func.id == "tuple"
        and len(generator_call.args) == 1
        and isinstance(generator_call.args[0], ast.GeneratorExp)
    ):
        raise StaticCoverageError(f"unexpected production target AST: {ast.dump(generator_call, include_attributes=False)}")
    generator = generator_call.args[0]
    if len(generator.generators) != 2:
        raise StaticCoverageError(f"unexpected production target generators: {ast.dump(generator, include_attributes=False)}")
    first, second = generator.generators
    if not (isinstance(first.iter, ast.Name) and first.iter.id == "RUNS"):
        raise StaticCoverageError(f"production runs are not sourced from RUNS: {ast.dump(first, include_attributes=False)}")
    suffixes = restricted_literal(second.iter, constants)
    element_shape = ast.dump(generator.elt, include_attributes=False)
    expected_names = {node.id for node in ast.walk(generator.elt) if isinstance(node, ast.Name)}
    if not isinstance(generator.elt, ast.JoinedStr) or expected_names != {"run_id", "suffix"}:
        raise StaticCoverageError(f"unexpected production target format: {element_shape}")
    run_targets = tuple(
        f"{run[0]}/{run[0]}_{suffix}"
        for run in constants["RUNS"]
        for suffix in suffixes
    )
    return (constants["PRODUCTION_LAUNCH_RECORD_FILENAME"],) + tuple(constants["PRODUCTION_ROOT_TARGETS"]) + run_targets


def static_collision_ids(test_tree, production_targets):
    expression = assignment_value(test_tree, "D1A_COLLISION_IDS")
    if not (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "tuple"
        and len(expression.args) == 1
        and isinstance(expression.args[0], ast.GeneratorExp)
    ):
        raise StaticCoverageError(f"unexpected collision-ID AST: {ast.dump(expression, include_attributes=False)}")
    generator = expression.args[0]
    if len(generator.generators) != 1:
        raise StaticCoverageError(f"unexpected collision-ID generators: {ast.dump(generator, include_attributes=False)}")
    source = generator.generators[0].iter
    if not (
        isinstance(source, ast.Attribute)
        and isinstance(source.value, ast.Name)
        and source.value.id == "o"
        and source.attr == "PRODUCTION_TARGETS"
    ):
        raise StaticCoverageError(f"collision IDs do not reference production targets: {ast.dump(source, include_attributes=False)}")
    rendered = ast.unparse(generator.elt)
    if "collision_target_" not in rendered or ".replace('/', '__').replace('.', '_')" not in rendered:
        raise StaticCoverageError(f"unexpected collision-ID transformation: {ast.dump(generator.elt, include_attributes=False)}")
    return tuple(f"collision_target_{target.replace('/', '__').replace('.', '_')}" for target in production_targets)


def static_d1a_coverage(test_path, runner_path):
    test_tree = ast.parse(test_path.read_text(encoding="utf-8"), filename=str(test_path))
    runner_tree = ast.parse(runner_path.read_text(encoding="utf-8"), filename=str(runner_path))
    production_targets = static_production_targets(runner_tree)
    if len(production_targets) != 25:
        raise StaticCoverageError(f"expected 25 production targets, found {len(production_targets)}")
    initial_required = restricted_literal(assignment_value(test_tree, "D1A_REQUIRED_CASE_IDS"), {})
    collision_ids = static_collision_ids(test_tree, production_targets)
    constants = {"D1A_COLLISION_IDS": collision_ids}
    update_calls = [
        node.value
        for node in test_tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "D1A_REQUIRED_CASE_IDS"
        and node.value.func.attr == "update"
    ]
    if len(update_calls) != 1 or len(update_calls[0].args) != 1 or update_calls[0].keywords:
        raise StaticCoverageError(f"unexpected required-ID update AST: {[ast.dump(x, include_attributes=False) for x in update_calls]}")
    required_ids = set(initial_required)
    required_ids.update(restricted_literal(update_calls[0].args[0], constants))

    parameterized = [node for node in test_tree.body if isinstance(node, ast.FunctionDef) and node.name == "test_d1a_phase1"]
    if len(parameterized) != 1:
        raise StaticCoverageError(f"expected one matrix test, found {len(parameterized)}")
    decorators = [decorator for decorator in parameterized[0].decorator_list if isinstance(decorator, ast.Call)]
    if len(decorators) != 1 or len(decorators[0].args) < 2:
        raise StaticCoverageError(f"unexpected matrix decorator AST: {[ast.dump(x, include_attributes=False) for x in decorators]}")
    ids_expression = decorators[0].args[1]
    if not (
        isinstance(ids_expression, ast.Call)
        and isinstance(ids_expression.func, ast.Name)
        and ids_expression.func.id == "sorted"
        and len(ids_expression.args) == 1
        and isinstance(ids_expression.args[0], ast.Name)
        and ids_expression.args[0].id == "D1A_REQUIRED_CASE_IDS"
        and not ids_expression.keywords
    ):
        raise StaticCoverageError(f"collected parameter IDs are not statically supported: {ast.dump(ids_expression, include_attributes=False)}")
    collected_ids = sorted(required_ids)

    coverage_functions = [
        node.name
        for node in test_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "test_d1a_coverage"
    ]
    if len(coverage_functions) != 1:
        raise StaticCoverageError(f"expected one independent coverage function, found {coverage_functions}")
    return {
        "required_ids": sorted(required_ids),
        "collected_ids": collected_ids,
        "coverage_function": coverage_functions[0],
        "required_source_ast": ast.dump(assignment_value(test_tree, "D1A_REQUIRED_CASE_IDS"), include_attributes=False),
        "collected_source_ast": ast.dump(ids_expression, include_attributes=False),
    }


def build_artifacts():
    runner = PROJECT_ROOT / "fermion/cp10/oracle_a_p0_10.py"
    tests = (
        PROJECT_ROOT / "tests/test_cp10_oracle_a_runspec_p0_10.py",
        PROJECT_ROOT / "tests/test_cp10_oracle_a_launch_payload_p0_10.py",
        PROJECT_ROOT / "tests/test_cp10_oracle_a_filesystem_contract_p0_10.py",
    )
    receipt = PROJECT_ROOT / "protocols/cp10_p0_10_FREEZE_RECEIPT.json"
    phase1_readiness = OUTPUT_DIR / "r2a2a2s1td1a_phase1_readiness_audit.json"
    attempt_025 = ATTEMPTS_DIR / "attempt_025_d1a_phase1_manifest.json"
    require_hash(receipt, RECEIPT_SHA256)
    require_hash(phase1_readiness, PHASE1_READINESS_SHA256)
    require_hash(attempt_025, ATTEMPT_025_SHA256)
    if sha256_file(runner) != RUNNER_SHA256 or runner.stat().st_size != RUNNER_BYTE_COUNT:
        raise RuntimeError("attempt-030 runner authority mismatch")

    coverage = static_d1a_coverage(tests[-1], runner)
    required_ids = coverage["required_ids"]
    collected_ids = coverage["collected_ids"]
    unique_ids = sorted(set(collected_ids))
    missing_ids = sorted(set(required_ids) - set(collected_ids))
    unexpected_ids = sorted(set(collected_ids) - set(required_ids))
    duplicate_ids = sorted({item for item in collected_ids if collected_ids.count(item) > 1})
    if (len(required_ids), len(collected_ids), len(unique_ids)) != (49, 49, 49):
        raise StaticCoverageError("D1A required/collected/unique count mismatch")
    if missing_ids or unexpected_ids or duplicate_ids:
        raise StaticCoverageError(f"D1A ID discrepancy: missing={missing_ids}, unexpected={unexpected_ids}, duplicate={duplicate_ids}")

    source_manifest = {
        "schema_version": "cp10-p0.10-oracle-a-d1a-source-manifest-v1",
        "protocol_id": "CP10-P0.10",
        "d1a_contract_version": "R2a.2A.2-S1T-D1A",
        "status": "PASS",
        "source_and_tests": [file_record(runner), *(file_record(path) for path in tests)],
        "freeze_receipt": {"path": relative_path(receipt), "sha256": RECEIPT_SHA256},
        "output_contract_sha256": OUTPUT_CONTRACT_SHA256,
        "canonical_target_hashes": {
            "candidate_24_targets_sha256": TARGET_24_SHA256,
            "complete_25_targets_sha256": TARGET_25_SHA256,
        },
        "phase1_evidence": {
            "readiness": {"path": relative_path(phase1_readiness), "sha256": PHASE1_READINESS_SHA256},
            "attempt_025": {"path": relative_path(attempt_025), "sha256": ATTEMPT_025_SHA256},
        },
        "production_source_manifest_regenerated": False,
        "production_source_manifest_path": "artifacts/cp10_p0_10_oracle_a/source_manifest.json",
        "canonical_json_terminal_newline": True,
    }
    source_bytes = canonical_bytes(source_manifest)
    source_hash = sha256_bytes(source_bytes)

    case_coverage = {
        "schema_version": "cp10-p0.10-oracle-a-d1a-case-coverage-v1",
        "required_ids": required_ids,
        "collected_ids": collected_ids,
        "counts": {"required": 49, "collected": 49, "unique": 49, "valid": 4, "invalid": 45, "FilesystemAuthorizationError": 43, "signature_level_TypeError": 2},
        "missing_ids": missing_ids,
        "unexpected_ids": unexpected_ids,
        "duplicate_ids": duplicate_ids,
        "static_extraction": {
            "required_source_ast": coverage["required_source_ast"],
            "collected_source_ast": coverage["collected_source_ast"],
            "imports_or_execution_used": False,
        },
        "independent_coverage": {
            "node_id": f"tests/test_cp10_oracle_a_filesystem_contract_p0_10.py::{coverage['coverage_function']}",
            "status": "PASS",
            "included_in_matrix_ids": False,
        },
        "status": "PASS",
    }
    coverage_bytes = canonical_bytes(case_coverage)
    coverage_hash = sha256_bytes(coverage_bytes)

    test_manifest = {
        "schema_version": "cp10-p0.10-oracle-a-d1a-test-manifest-v1",
        "historical_focused_test_execution": {
            "command_interpreter": HISTORICAL_TEST_INTERPRETER,
            "interpreter_exists_currently": Path(HISTORICAL_TEST_INTERPRETER).is_file(),
            "observed_collection": 590,
            "observed_result": "590 passed in 2.81s",
            "versions": {
                "python": "UNAVAILABLE_IN_PRESERVED_TEST_EVIDENCE",
                "numpy": "UNAVAILABLE_IN_PRESERVED_TEST_EVIDENCE",
                "pytest": "UNAVAILABLE_IN_PRESERVED_TEST_EVIDENCE",
            },
            "version_evidence_sources_checked": [
                "artifacts/cp10_p0_10_oracle_a/r2a2a2s1tc2_test_manifest.json",
                "artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1a_phase1_readiness_audit.json",
                "artifacts/cp10_p0_10_oracle_a/attempts/attempt_025_d1a_phase1_manifest.json",
            ],
        },
        "current_evidence_writer_execution": {
            "executable": CURRENT_WRITER_INTERPRETER,
            "python_version": CURRENT_WRITER_PYTHON_VERSION,
            "observed_executable": sys.executable,
            "observed_python_version": platform.python_version(),
            "standard_library_only": True,
            "numpy_imported_or_required": False,
            "pytest_imported_or_required": False,
        },
        "compile": {"status": "PASS", "targets": [relative_path(runner), *(relative_path(path) for path in tests)]},
        "collection": {
            "command": "G:\\MyAIproject.venv\\Scripts\\python.exe -m pytest --collect-only -q -p no:cacheprovider tests/test_cp10_oracle_a_runspec_p0_10.py tests/test_cp10_oracle_a_launch_payload_p0_10.py tests/test_cp10_oracle_a_filesystem_contract_p0_10.py",
            "collected": 590,
            "status": "PASS",
        },
        "focused_pytest": {
            "command": "G:\\MyAIproject.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider --basetemp G:\\MyAIproject.pytest-d1a-attempt-030 tests/test_cp10_oracle_a_runspec_p0_10.py tests/test_cp10_oracle_a_launch_payload_p0_10.py tests/test_cp10_oracle_a_filesystem_contract_p0_10.py",
            "passed": 590,
            "failed": 0,
            "duration_seconds": 2.81,
            "status": "PASS",
        },
        "collection_arithmetic": {"pre_d1a_baseline": 540, "d1a_matrix": 49, "independent_coverage": 1, "total": 590},
        "case_counts": case_coverage["counts"],
        "missing_ids": [],
        "unexpected_ids": [],
        "duplicate_ids": [],
        "independent_coverage_status": "PASS",
        "production_isolation": "PASS",
        "status": "PASS",
    }
    test_bytes = canonical_bytes(test_manifest)
    test_hash = sha256_bytes(test_bytes)

    readiness = {
        "schema_version": "cp10-p0.10-oracle-a-d1a-readiness-audit-v1",
        "protocol_id": "CP10-P0.10",
        "status": "BLOCKED_PENDING_R2A2A2_S1T_D1B_AUTHORITY_ORDER_AND_SOURCE_MANIFEST",
        "evidence": {
            "source_manifest": {"path": relative_path(ORDERED_TARGETS[0]), "sha256": source_hash},
            "case_coverage": {"path": relative_path(ORDERED_TARGETS[1]), "sha256": coverage_hash},
            "test_manifest": {"path": relative_path(ORDERED_TARGETS[2]), "sha256": test_hash},
        },
        "d1a_path_safety": "PASS",
        "d1a_collision_engine": "PASS",
        "case_coverage": "PASS",
        "focused_regression": "PASS",
        "production_isolation": "PASS",
        "d1b": "NOT_STARTED",
        "d2": "NOT_STARTED",
        "controlled_probe": "NOT_RUN",
        "launch": "UNAUTHORIZED",
        "integration_calls": 0,
        "frozen_trajectories": 0,
    }
    readiness_bytes = canonical_bytes(readiness)
    readiness_hash = sha256_bytes(readiness_bytes)

    attempt_manifest = {
        "schema_version": "cp10-p0.10-oracle-a-d1a-attempt-manifest-v1",
        "attempt": 32,
        "status": "BLOCKED_PENDING_R2A2A2_S1T_D1B_AUTHORITY_ORDER_AND_SOURCE_MANIFEST",
        "attempt_031": {"failure": "ModuleNotFoundError: No module named 'fermion'", "promotion_occurred": False},
        "writer": {"path": relative_path(WRITER_PATH), "sha256": sha256_file(WRITER_PATH), "compile": "PASS", "project_root_insertion_corrected": True},
        "artifacts": [
            {"path": relative_path(ORDERED_TARGETS[0]), "sha256": source_hash},
            {"path": relative_path(ORDERED_TARGETS[1]), "sha256": coverage_hash},
            {"path": relative_path(ORDERED_TARGETS[2]), "sha256": test_hash},
            {"path": relative_path(ORDERED_TARGETS[3]), "sha256": readiness_hash},
        ],
        "source_or_test_changed": False,
        "production_authority_changed": False,
        "production_source_manifest_regenerated": False,
        "launch_record_created": False,
        "production_output_created": False,
        "integration_calls": 0,
        "frozen_trajectories": 0,
    }
    attempt_bytes = canonical_bytes(attempt_manifest)
    items = tuple(zip(ORDERED_TARGETS, (source_bytes, coverage_bytes, test_bytes, readiness_bytes, attempt_bytes)))
    assert_exact_targets(items)
    return items


def validate_artifacts(items):
    assert_exact_targets(items)
    decoded = [strict_parse(data) for _, data in items]
    for (_, data), value in zip(items, decoded):
        if canonical_bytes(value) != data:
            raise RuntimeError("non-canonical proposed artifact")
    hashes = [sha256_bytes(data) for _, data in items]
    readiness_evidence = decoded[3]["evidence"]
    for index, key in enumerate(("source_manifest", "case_coverage", "test_manifest")):
        if readiness_evidence[key]["sha256"] != hashes[index]:
            raise RuntimeError(f"readiness hash binding mismatch: {key}")
    if [item["sha256"] for item in decoded[4]["artifacts"]] != hashes[:4]:
        raise RuntimeError("attempt artifact hash binding mismatch")
    if decoded[1]["counts"] != decoded[2]["case_counts"]:
        raise RuntimeError("case-count binding mismatch")
    if decoded[1]["missing_ids"] or decoded[1]["unexpected_ids"] or decoded[1]["duplicate_ids"]:
        raise RuntimeError("case coverage discrepancies present")
    return [{"path": relative_path(path), "sha256": digest, "byte_count": len(data)} for (path, data), digest in zip(items, hashes)]


def atomic_write(path, data):
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".attempt_032_evidence_", suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        if path.read_bytes() != data:
            raise RuntimeError(f"atomic write verification failed: {relative_path(path)}")
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def commit_artifacts(items):
    assert_exact_targets(items)
    validate_artifacts(items)
    for path, data in items:
        atomic_write(path, data)


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-only", action="store_true")
    modes.add_argument("--commit", action="store_true")
    arguments = parser.parse_args()
    items = build_artifacts()
    summary = validate_artifacts(items)
    if arguments.commit:
        commit_artifacts(items)
    for record in summary:
        print(record["path"], record["sha256"], record["byte_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
