from pathlib import Path
import json
import numpy as np
import pytest
import torch

from fermion.ai_g1.ai_g2s_r1 import (DeterministicSplitFactory, FullPairedRunner, ProtocolFailure, FinalTestAccessGate, atomic_checkpoint,
    atomic_json, build_capacity_model, canonical_json_sha256, canonical_source_manifest, deterministic_hierarchical_bootstrap, finalize_condition_records,
    load_checkpoint, load_frozen_protocol, normalized_mse, parseval_audit, radial_frequency_bins, sha256, verify_json_content, verify_source_manifest)


ROOT=Path("G:/MyAIproject")

def test_p11_hashes_and_parse_are_authoritative():
    cfg=load_frozen_protocol(ROOT)
    assert cfg["bootstrap"]["resamples"]==10000 and cfg["training_seeds"]==[0,1,2]

def test_splits_regenerate_and_test_isolated():
    factory=DeterministicSplitFactory(load_frozen_protocol(ROOT)); a=factory.generate("tabular_control","calibration",limit=2); b=factory.generate("tabular_control","calibration",limit=2)
    assert torch.equal(a.x,b.x) and a.x.shape==(2,1,8,8)
    with pytest.raises(ProtocolFailure): factory.generate("tabular_control","test_id",limit=2)
    gate=FinalTestAccessGate(); gate.select("tabular_control","spectral",0)
    assert factory.generate("tabular_control","test_id",limit=2,gate=gate,model="spectral",training_seed=0).y.shape==(2,1)
    assert factory.generate("coordinate_permutation","calibration",limit=2).x.shape==(2,2,32,32)
    gate.select("cross_resolution_fields","spectral",0)
    assert factory.generate("cross_resolution_fields","test_ood",limit=2,gate=gate,model="spectral",training_seed=0,resolution=64).x.shape[-2:]==(64,64)

def test_capacity_contract_and_resolution_independent_shapes():
    cfg=load_frozen_protocol(ROOT)
    for kind in cfg["models"]:
        model=build_capacity_model(kind,dimension=2,in_channels=2,out_channels=1,config=cfg)
        ratio=sum(p.numel() for p in model.parameters())/cfg["model_capacity_contract"]["target_trainable_parameters"]
        assert .95<=ratio<=1.05
        assert model(torch.randn(1,2,32,32)).shape[-2:]==(32,32)
        assert model(torch.randn(1,2,64,64)).shape[-2:]==(64,64)

def test_atomic_resume_and_paired_bootstrap_are_deterministic(tmp_path):
    path=tmp_path/"checkpoint.pt"; atomic_checkpoint(path,{"condition_id":"elliptic:spectral:0","step":2,"state":{"x":1}})
    assert load_checkpoint(path,"elliptic:spectral:0")["step"]==2
    loss=np.array([[1.,2.],[1.1,2.1],[.9,1.9]]); assert deterministic_hierarchical_bootstrap(loss,loss)==deterministic_hierarchical_bootstrap(loss,loss)

def test_normalized_mse_and_nonfinite_failure():
    assert normalized_mse(torch.ones(2,1),torch.zeros(2,1),torch.zeros(1),torch.ones(1)).shape==(2,)
    with pytest.raises(ProtocolFailure): normalized_mse(torch.ones(1,1),torch.zeros(1,1),torch.zeros(1),torch.tensor([1e-8]))

def test_parseval_and_retained_nyquist_frequency_bins():
    audit=parseval_audit(torch.randn(3,32,32)); assert audit["absolute_error"] < 1e-5
    bins=radial_frequency_bins(32,32); assert len(bins["retained_counts"])==16 and bins["excluded_corner_shell_count"]>0

def test_finalizer_fails_closed_on_missing_conditions():
    with pytest.raises(ProtocolFailure): finalize_condition_records([],load_frozen_protocol(ROOT))

def test_full_entry_point_is_gated_before_any_test_access(tmp_path):
    runner=FullPairedRunner(ROOT,tmp_path)
    with pytest.raises(ProtocolFailure,match="gated"):
        runner.run()

def test_byte_exact_json_provenance_does_not_fall_back_to_canonical_json(tmp_path):
    artifact=tmp_path/"artifact.json"; artifact.write_text('{\n  "a": 1\n}\n',encoding="utf-8")
    raw=sha256(artifact); canonical=canonical_json_sha256(artifact)
    assert verify_json_content(artifact,raw_sha256=raw,canonical_json_sha256_expected=canonical)["raw_sha256"]==raw
    artifact.write_text('{"a":1}',encoding="utf-8")
    assert canonical_json_sha256(artifact)==canonical
    with pytest.raises(ProtocolFailure,match="raw SHA-256"):
        verify_json_content(artifact,raw_sha256=raw,canonical_json_sha256_expected=canonical)

def test_source_manifest_verifies_the_fixed_complete_source_set(tmp_path):
    sources=[ROOT/relative for relative in ("fermion/ai_g1/ai_g2s_r1.py","fermion/ai_g1/ai_g2s.py","fermion/ai_g1/spectral.py","fermion/ai_g1/diagnostics.py","fermion/hr/reference_193.py")]
    manifest=tmp_path/"source_manifest.json"; atomic_json(manifest,canonical_source_manifest(ROOT,sources)); result=verify_source_manifest(ROOT,manifest,manifest_raw_sha256=sha256(manifest))
    assert result["verified_entries"]==5
