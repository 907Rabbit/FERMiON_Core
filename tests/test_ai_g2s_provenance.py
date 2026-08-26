import json

from fermion.ai_g1.ai_g2s_provenance import (sha256_file, verify_detached_preexecution_provenance,
                                             verify_preexecution_source_manifest)


def source_bundle(tmp_path):
    root = tmp_path / "project"
    for relative, content in {
        "fermion/ai_g1/ai_g2s.py": "MODEL = 1\n",
        "fermion/hr/reference_193.py": "REFERENCE = 193\n",
        "configs/ai_g2s_p1_0.json": "{}\n",
        "configs/ai_g2s_p1_1.json": "{}\n",
    }.items():
        path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
    manifest = {"format": "sha256-two-space-relative-path-v1", "protocol_id": "AI-G2S-P1.1",
                "p10_sha256": sha256_file(root / "configs/ai_g2s_p1_0.json"),
                "p11_sha256": sha256_file(root / "configs/ai_g2s_p1_1.json"),
                "entries": [{"path": path, "sha256": sha256_file(root / path)} for path in
                            ("fermion/ai_g1/ai_g2s.py", "fermion/hr/reference_193.py")]}
    path = root / "artifacts" / "source_manifest.json"; path.parent.mkdir(); path.write_text(json.dumps(manifest), encoding="utf-8")
    return root, path


def test_preexecution_verifier_reports_hash_matches_without_execution(tmp_path):
    root, manifest = source_bundle(tmp_path)
    result = verify_preexecution_source_manifest(root=root, manifest_path=manifest)
    assert result["verified"] and result["execution"] == "NOT_RUN"


def test_preexecution_verifier_detects_source_drift(tmp_path):
    root, manifest = source_bundle(tmp_path)
    (root / "fermion/ai_g1/ai_g2s.py").write_text("MODEL = 2\n", encoding="utf-8")
    result = verify_preexecution_source_manifest(root=root, manifest_path=manifest)
    assert not result["verified"] and not result["entries"][0]["match"]


def test_detached_preexecution_verifier_preserves_gated_status(tmp_path):
    root, source_manifest = source_bundle(tmp_path)
    (root / "scripts").mkdir(); (root / "scripts" / "launch.ps1").write_text("safe\n")
    (root / "tests").mkdir(); (root / "tests" / "test.py").write_text("pass\n")
    coverage = root / "artifacts" / "ai_g2s_r1" / "p1_1_protocol_coverage.json"; coverage.parent.mkdir(); coverage.write_text("{}\n")
    environment = root / "artifacts" / "environment.json"; environment.write_text("{}\n")
    detached = {"format": "FERMiON-AI-G2S-P1.1-detached-provenance-v2",
                "protocol": {"p10_raw_sha256": sha256_file(root / "configs/ai_g2s_p1_0.json"), "p11_raw_sha256": sha256_file(root / "configs/ai_g2s_p1_1.json"), "coverage_audit_raw_sha256": sha256_file(coverage)},
                "implementation": {"runner": {"path": "fermion/ai_g1/ai_g2s.py", "raw_sha256": sha256_file(root / "fermion/ai_g1/ai_g2s.py")}, "launcher": {"path": "scripts/launch.ps1", "raw_sha256": sha256_file(root / "scripts/launch.ps1")}, "tests": {"path": "tests/test.py", "raw_sha256": sha256_file(root / "tests/test.py")}},
                "source_manifest": {"path": "artifacts/source_manifest.json", "raw_sha256": sha256_file(source_manifest)},
                "preexecution_artifacts": {"environment": {"path": "artifacts/environment.json", "raw_sha256": sha256_file(environment)}},
                "frozen_reference": {"path": "fermion/hr/reference_193.py", "raw_sha256": sha256_file(root / "fermion/hr/reference_193.py")},
                "scientific_status": {"full_paired_execution": "GATED", "final_test_predictions": "NONE", "spectral_utility": "UNEARNED"}}
    path = root / "artifacts" / "detached.json"; path.write_text(json.dumps(detached), encoding="utf-8")
    result = verify_detached_preexecution_provenance(root=root, provenance_path=path)
    assert result["verified"] and result["scientific_status"]["full_paired_execution"] == "GATED"
