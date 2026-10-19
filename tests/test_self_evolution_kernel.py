from __future__ import annotations

import json

from fermion.adapters.evolution_kernel import EvolutionKernelAdapter, EvolutionKernelConfig
from fermion.control_plane import default_control_plane
from fermion.self_evolution_kernel import FERMiONKernel
from fermion.software.application import Action


def test_separate_kernel_is_deterministic_and_hashes_manifests(tmp_path):
    first = FERMiONKernel(seed=7, workspace=tmp_path / "first")
    second = FERMiONKernel(seed=7, workspace=tmp_path / "second")
    first_result = first.run_evolution(3, verbose=False)
    second_result = second.run_evolution(3, verbose=False)
    assert first_result == second_result
    assert first_result["audit_chain_verified"] is True
    manifests = first.promoted_candidates + first.rejected_candidates
    assert len(manifests) == 3
    assert all(len(item.manifest_sha256) == 64 for item in manifests)


def test_kernel_adapter_exposes_bounded_status_and_simulation(tmp_path):
    adapter = EvolutionKernelAdapter(EvolutionKernelConfig(tmp_path / "kernel", max_cycles=4))
    status = adapter.execute(Action("status"))
    assert status.success
    assert status.details["separate_from_safe_self_evolver"] is True
    result = adapter.execute(Action("simulate", {"cycles": 3, "seed": 11}))
    assert result.success
    assert result.details["simulation"]["total_cycles"] == 3
    assert result.details["simulation"]["audit_chain_verified"] is True
    assert result.details["persistent_outputs_created"] is False
    assert not adapter.execute(Action("simulate", {"cycles": True})).success
    assert not adapter.execute(Action("simulate", {"cycles": 5})).success


def test_llm_control_plane_can_use_separate_kernel_without_replacing_safe_evolver(tmp_path):
    plane = default_control_plane(tmp_path)
    manifest = plane.manifest()
    assert "self_evolver" in manifest
    assert "self_evolution_kernel" in manifest
    assert [item["operation"] for item in manifest["self_evolution_kernel"]["capabilities"]] == [
        "status", "simulate",
    ]
    plan = plane.parse_plan("Simulate two CW-71 cycles", json.dumps({
        "summary": "Run the separate self-evolution simulation.",
        "actions": [{
            "application": "self_evolution_kernel",
            "operation": "simulate",
            "arguments": {"cycles": 2, "seed": 5},
        }],
        "requires_approval": False,
    }))
    report = plane.execute(plan, approved=False)
    assert report.validation.valid
    assert report.records[0].result.details["simulation"]["total_cycles"] == 2
