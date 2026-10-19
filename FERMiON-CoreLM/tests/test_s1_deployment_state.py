"""Current-state deployment checks after the authorized 2026-09-20 S1 alias cutover.

These assert the live production state (not historical pre-cutover evidence):
the deployed GGUF lineage is S1, w85 is retained only as rollback, and the
production alias files on disk hold the qualified S1 weights.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST = ROOT / 'exports' / 'production_manifest.json'
LINEAGE = ROOT / 'checkpoints' / 's0_lineage.json'

ACTIVE_DEPLOYED_GGUF_LINEAGE = 's1_long@819200'
ROLLBACK_LINEAGE = 'w85@192000'
F32_SHA256 = '5AC11A681A1F721B67512615F9A7B9D6ABFD826F0E47A1BC5893842E38896BFD'
Q8_SHA256 = 'B66F14EDEEB64F5B1643800C0A6149FC9BC16F5CF2E3917D36E8720D089F54A1'


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def test_production_manifest_reflects_s1_cutover():
    m = _load(PRODUCTION_MANIFEST)
    assert m['active_deployed_gguf_lineage'] == ACTIVE_DEPLOYED_GGUF_LINEAGE
    assert m['active_champion'] == ACTIVE_DEPLOYED_GGUF_LINEAGE
    assert m['canonical_model_champion'] == ACTIVE_DEPLOYED_GGUF_LINEAGE
    assert m['active_f32_sha256'] == F32_SHA256
    assert m['active_q8_0_sha256'] == Q8_SHA256
    assert m['rollback']['deployed_gguf_lineage'] == ROLLBACK_LINEAGE


def test_production_alias_files_hold_s1_weights():
    m = _load(PRODUCTION_MANIFEST)
    assert _sha256(m['production_f32_alias']) == F32_SHA256
    assert _sha256(m['production_q8_alias']) == Q8_SHA256


def test_lineage_deployed_block_aligned_to_s1():
    dep = _load(LINEAGE)['deployed_gguf_artifact']
    assert dep['champion'] == ACTIVE_DEPLOYED_GGUF_LINEAGE
    assert dep['f32_sha256'] == F32_SHA256
    assert dep['q8_0_sha256'] == Q8_SHA256
    assert dep['rollback_lineage'] == ROLLBACK_LINEAGE
    assert dep['production_manifest_sha256'] == _sha256(PRODUCTION_MANIFEST)
