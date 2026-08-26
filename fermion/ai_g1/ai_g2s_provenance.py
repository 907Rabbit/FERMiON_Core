"""Read-only verification of the frozen AI-G2S pre-execution source bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def verify_preexecution_source_manifest(*, root: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify declared source/config hashes without importing or running AI-G2S."""
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    if root not in manifest_path.parents or not manifest_path.is_file():
        raise FileNotFoundError("AI-G2S source manifest is unavailable inside the project root")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "sha256-two-space-relative-path-v1" or manifest.get("protocol_id") != "AI-G2S-P1.1":
        raise ValueError("unsupported AI-G2S source manifest contract")
    entries: list[dict[str, object]] = []
    for item in manifest.get("entries", []):
        relative = str(item["path"])
        target = (root / relative).resolve()
        expected = str(item["sha256"]).upper()
        if root not in target.parents or not target.is_file():
            entries.append({"path": relative, "expected_sha256": expected, "actual_sha256": None, "match": False})
            continue
        actual = sha256_file(target)
        entries.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected})
    configs = {"p10": "configs/ai_g2s_p1_0.json", "p11": "configs/ai_g2s_p1_1.json"}
    config_results: dict[str, dict[str, object]] = {}
    for name, relative in configs.items():
        target = root / relative
        expected = str(manifest[f"{name}_sha256"]).upper()
        actual = sha256_file(target) if target.is_file() else None
        config_results[name] = {"path": relative, "expected_sha256": expected, "actual_sha256": actual,
                                "match": actual == expected}
    return {"protocol_id": manifest["protocol_id"], "manifest": str(manifest_path), "entries": entries,
            "configs": config_results, "verified": all(item["match"] for item in entries) and
            all(item["match"] for item in config_results.values()), "execution": "NOT_RUN"}


def verify_detached_preexecution_provenance(*, root: Path, provenance_path: Path) -> dict[str, Any]:
    """Verify fixed-file hashes in the detached P1.1 envelope; never launch work."""
    root = root.resolve(); provenance_path = provenance_path.resolve()
    if root not in provenance_path.parents or not provenance_path.is_file():
        raise FileNotFoundError("AI-G2S detached provenance is unavailable inside the project root")
    payload = json.loads(provenance_path.read_text(encoding="utf-8"))
    if payload.get("format") != "FERMiON-AI-G2S-P1.1-detached-provenance-v2":
        raise ValueError("unsupported detached AI-G2S provenance contract")
    descriptors: list[tuple[str, str, str]] = [
        ("p10", "configs/ai_g2s_p1_0.json", payload["protocol"]["p10_raw_sha256"]),
        ("p11", "configs/ai_g2s_p1_1.json", payload["protocol"]["p11_raw_sha256"]),
        ("coverage", "artifacts/ai_g2s_r1/p1_1_protocol_coverage.json", payload["protocol"]["coverage_audit_raw_sha256"]),
        ("source_manifest", payload["source_manifest"]["path"], payload["source_manifest"]["raw_sha256"]),
        ("frozen_reference", payload["frozen_reference"]["path"], payload["frozen_reference"]["raw_sha256"]),
    ]
    for name, value in payload["implementation"].items():
        descriptors.append((f"implementation:{name}", value["path"], value["raw_sha256"]))
    for name, value in payload["preexecution_artifacts"].items():
        descriptors.append((f"artifact:{name}", value["path"], value["raw_sha256"]))
    results = []
    for name, relative, expected in descriptors:
        target = (root / relative).resolve(); actual = sha256_file(target) if root in target.parents and target.is_file() else None
        results.append({"name": name, "path": relative, "expected_sha256": str(expected).upper(),
                        "actual_sha256": actual, "match": actual == str(expected).upper()})
    status = payload["scientific_status"]
    return {"protocol_id": "AI-G2S-P1.1", "detached_provenance": str(provenance_path), "files": results,
            "verified": all(item["match"] for item in results), "scientific_status": status, "execution": "NOT_RUN"}
