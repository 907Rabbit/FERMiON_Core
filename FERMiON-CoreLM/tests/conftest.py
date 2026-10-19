import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _run_in_corelm_root():
    """CoreLM tests use paths relative to the FERMiON-CoreLM package root
    (e.g. ``data/tokenizer.json``) and spawn subprocesses that import
    ``fermion_llm`` from the current working directory, so they must run
    with that directory as CWD regardless of where pytest was launched.
    Restore the previous CWD afterwards so sibling suites are unaffected."""
    previous = Path.cwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(previous)


@pytest.fixture(autouse=True)
def _isolate_locked_guard_depth():
    """Test-boundary isolation for the process-global locked-data audit guard.

    The guard in fermion_llm.training.s1_calibration is reference-counted, but one
    legitimate caller lives in a frozen gate-source file (s1_boundary_finalization_audit
    .no_locked_resolution) that cannot be changed, so an activation it makes is not
    released at scope exit. That is harmless in a real run (enforcement staying on only
    protects more), but across tests in one process it could let one test's leftover
    activation poison the next.

    This fixture snapshots the exact activation depth before each test and restores
    exactly that depth afterwards. It never forces the depth to zero, never disables
    enforcement while a test runs, and never touches the permanent audit hook, so
    legitimate nested protection inside a test stays real and a test that enters with
    protection active leaves with it equally active. It exists only under tests/ and no
    production code depends on it. If the depth is not introspectable (API drift), it
    fails loudly rather than silently weakening protection."""
    from fermion_llm.training import s1_calibration as cal
    before = cal._GUARD_DEPTH
    if not isinstance(before, int):
        raise RuntimeError('locked-data guard depth is not introspectable; refusing to run')
    try:
        yield
    finally:
        after = getattr(cal, '_GUARD_DEPTH', None)
        if not isinstance(after, int):
            raise RuntimeError('locked-data guard depth is not introspectable; refusing to silently weaken protection')
        cal._GUARD_DEPTH = before
