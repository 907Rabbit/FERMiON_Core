from __future__ import annotations

import json

import pytest

import fermion.safe_self_evolver as self_evolver_module
from fermion.safe_self_evolver import (ENGINE_ID, EvolutionError, Genome, SafeSelfEvolver,
                                       build_parser, run_self_tests, source_for_genome,
                                       validate_strategy_source)


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


def test_promoted_versions_are_atomic_listable_and_byte_identical(tmp_path, monkeypatch):
    evolver = SafeSelfEvolver(tmp_path / "runtime")
    writes = []
    real_atomic_write = self_evolver_module.atomic_write_text

    def recording_write(path, text):
        writes.append(path)
        real_atomic_write(path, text)

    monkeypatch.setattr(self_evolver_module, "atomic_write_text", recording_write)
    genome = Genome((0.1, 0.0, 0.0, 0.0, 0.0, 0.0),
                    (True, False, False, False, False, False))
    seeds = {"training": 11, "validation": 22, "test": 33}
    promoted = evolver.promote(genome, 0.8, 0.9, 7, dataset_seeds=seeds)
    version_path = evolver.versions_path / "strategy_v0001.py"
    assert version_path in writes
    assert version_path.read_bytes() == evolver.active_path.read_bytes()
    assert evolver.list_versions() == [promoted]
    assert promoted["dataset_seeds"] == seeds
    assert not list(evolver.workspace.rglob("*.tmp"))


def test_rollback_cannot_move_forward_after_reaching_first_version(tmp_path):
    evolver = SafeSelfEvolver(tmp_path / "runtime")
    first = Genome((0.0,) * 6, (True, False, False, False, False, False))
    second = Genome((0.2, 0.0, 0.0, 0.0, 0.0, 0.0),
                    (True, False, False, False, False, False))
    evolver.promote(first, 1.0, 1.0, 1)
    evolver.promote(second, 0.9, 0.9, 2)
    evolver.rollback()
    with pytest.raises(EvolutionError, match="no previous promoted version"):
        evolver.rollback()


def test_rollback_verifies_the_restored_active_hash(tmp_path, monkeypatch):
    evolver = SafeSelfEvolver(tmp_path / "runtime")
    first = Genome((0.0,) * 6, (True, False, False, False, False, False))
    second = Genome((0.2, 0.0, 0.0, 0.0, 0.0, 0.0),
                    (True, False, False, False, False, False))
    evolver.promote(first, 1.0, 1.0, 1)
    evolver.promote(second, 0.9, 0.9, 2)
    real_atomic_write = self_evolver_module.atomic_write_text

    def corrupt_active(path, text):
        real_atomic_write(path, text + "\n# corrupted after validation\n" if path == evolver.active_path else text)

    monkeypatch.setattr(self_evolver_module, "atomic_write_text", corrupt_active)
    with pytest.raises(EvolutionError, match="restored active file hash mismatch"):
        evolver.rollback()


def test_state_binds_active_version_hash_and_genome(tmp_path):
    evolver = SafeSelfEvolver(tmp_path / "runtime")
    genome = Genome((0.0,) * 6, (True, False, False, False, False, False))
    evolver.promote(genome, 1.0, 1.0, 1)
    state = json.loads(evolver.state_path.read_text(encoding="utf-8"))
    state["active_version"] = 99
    evolver.state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(EvolutionError, match="active version does not match"):
        evolver.status()


def test_evolution_accepts_distinct_dataset_seeds_and_records_them(tmp_path):
    evolver = SafeSelfEvolver(tmp_path / "runtime")
    result = evolver.evolve(5, 1, 8, 0.999, train_seed=11, val_seed=22, test_seed=33)
    assert result["dataset_seeds"] == {"training": 11, "validation": 22, "test": 33}
    with pytest.raises(EvolutionError, match="must be distinct"):
        evolver.evolve(5, 1, 8, 0.1, train_seed=11, val_seed=11, test_seed=33)
    with pytest.raises(EvolutionError, match="must be integers"):
        evolver.evolve(True, 1, 8, 0.1)


def test_cli_exposes_versions_and_dataset_seed_overrides():
    parser = build_parser()
    versions = parser.parse_args(["versions"])
    assert versions.command == "versions"
    evolve = parser.parse_args([
        "evolve", "--train-seed", "11", "--val-seed", "22", "--test-seed", "33",
    ])
    assert (evolve.train_seed, evolve.val_seed, evolve.test_seed) == (11, 22, 33)
