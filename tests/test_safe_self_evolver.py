from __future__ import annotations

import pytest

from fermion.safe_self_evolver import (ENGINE_ID, EvolutionError, Genome, SafeSelfEvolver,
                                       run_self_tests, source_for_genome, validate_strategy_source)


def test_self_evolver_safety_and_provenance_contracts_pass():
    report = run_self_tests()
    assert report["passed"]
    assert len(report["checks"]) == 6


def test_malicious_source_is_rejected():
    with pytest.raises(EvolutionError, match="only math"):
        validate_strategy_source("import os\ndef predict(x):\n return os.system('unsafe')\n")


def test_feedback_evolution_and_rollback_are_auditable(tmp_path):
    evolver = SafeSelfEvolver(tmp_path / "runtime")
    assert evolver.status()["engine_id"] == ENGINE_ID
    feedback = evolver.record_feedback(1.25, 1.8, 2.0)
    assert feedback["x"] == 1.25 and feedback["target"] == 1.8 and feedback["weight"] == 2.0
    first = evolver.promote(Genome((0.0,) * 6, (True, False, False, False, False, False)), 1.0, 1.0, 1)
    second = evolver.promote(Genome((0.2, 0.0, 0.0, 0.0, 0.0, 0.0), (True, False, False, False, False, False)), .9, .9, 2)
    assert first["sha256"] != second["sha256"]
    event = evolver.rollback()
    assert event["to_version"] == 1
    assert evolver.status()["active_version"] == 1
