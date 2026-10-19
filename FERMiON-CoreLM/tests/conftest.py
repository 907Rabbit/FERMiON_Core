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
