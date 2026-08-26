"""Bounded GuardedExecutor proofs. CognitiveRuntime must not call subprocess itself."""

from __future__ import annotations

from pathlib import Path

from fermion.cognitive.evidence import ExecutionEvidence, utc_now
from fermion.hr.contracts import CandidateProgram, ProgramKind
from fermion.software.executor import GuardedExecutor
from fermion.software.validators import ExitCodeValidator, FileExistsValidator

_PRIME_PROGRAM = (
    "def primes(limit):\n"
    "    return [n for n in range(2, limit + 1) if all(n % d for d in range(2, int(n ** 0.5) + 1))]\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    print(primes(30))\n"
)

_PRIME_DRIVER = (
    "from pathlib import Path\n"
    f"source = { _PRIME_PROGRAM !r}\n"
    "Path('primes.py').write_text(source, encoding='utf-8')\n"
    "def primes(limit):\n"
    "    return [n for n in range(2, limit + 1) if all(n % d for d in range(2, int(n ** 0.5) + 1))]\n"
    "print(primes(30))\n"
)


def _stage(root: Path) -> Path:
    staging = (root / ".fermion_exec").resolve()
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def _commit_to_root(staging: Path, root: Path, relative: str) -> Path:
    source = staging / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


def run_prime_program(root: Path) -> ExecutionEvidence:
    staging = _stage(root)
    started = utc_now()
    candidate = CandidateProgram(
        "documented-primes", _PRIME_DRIVER, ProgramKind.PYTHON,
        declared_artifacts=("primes.py",), reversible=True, provenance="bounded_execution",
    )
    result = GuardedExecutor(staging).execute(candidate, FileExistsValidator("primes.py"), commit=True)
    artifact = _commit_to_root(staging, root, "primes.py")
    return ExecutionEvidence.create(
        ["guarded_executor", "primes.py"], root, result.return_code, result.stdout, result.stderr,
        started, [artifact],
    )


def run_workspace_proof(root: Path, relative: str, token: str) -> ExecutionEvidence:
    staging = _stage(root)
    started = utc_now()
    posix = relative.replace("\\", "/")
    driver = (
        "from pathlib import Path\n"
        f"token = {token!r}\n"
        f"path = Path({posix!r})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text('print(' + repr(token) + ')\\n', encoding='utf-8')\n"
        "print(token)\n"
    )
    candidate = CandidateProgram(
        "documented-workspace-proof", driver, ProgramKind.PYTHON,
        declared_artifacts=(posix,), reversible=True, provenance="bounded_execution",
    )
    result = GuardedExecutor(staging).execute(candidate, ExitCodeValidator(), commit=True)
    artifact = _commit_to_root(staging, root, posix)
    return ExecutionEvidence.create(
        ["guarded_executor", posix], root, result.return_code, result.stdout, result.stderr,
        started, [artifact],
    )
