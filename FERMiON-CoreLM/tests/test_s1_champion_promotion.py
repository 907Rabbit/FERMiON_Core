import copy
from pathlib import Path
import pytest
from scripts import s1_champion_promotion as p

def test_unique_gate_winner_and_consumption():
    receipt = p.verify_gate()
    assert receipt['decision']['winner'] == p.WINNER
    assert receipt['decision']['NEW_CHAMPION_APPROVED']
    assert receipt['consumption']['PROMOTION_V4_1_CONSUMED_FOR_S1_PROGRAM'] == 'YES'

def test_source_exact_hash():
    assert p.sha(p.SOURCE/'model.safetensors') == p.WINNER_HASH

def test_previous_champion_and_rollback():
    old = p.read(p.OUT/'rollback_manifest.json')
    assert old['previous_pointer']['checkpoint'] == 'w85@192000'
    path = Path(old['previous_pointer']['path'])
    assert p.sha(path/'model.safetensors') == p.OLD_HASH
    assert p.checkpoint_hashes(path) == old['previous_checkpoint_hashes']
    model, extra = p.r.load_checkpoint(path)
    assert extra['optimizer'] and extra['rng'] and extra['data_state']
    assert old['reload_verified'] and not old['locked_access_required']

def test_winner_full_state_reload_and_retained_roundtrip():
    proof = p.read(p.OUT/'champion_state_verification.json')
    assert proof['pass'] and proof['before'] == proof['after']
    with p.forbidden_runtime():
        for path in (p.SOURCE, p.RETAINED):
            model, opt, extra = p.r.restore(path)
            assert p.r.fingerprint(model, opt, extra['rng'], extra['data_state']) == proof['before']
            assert extra['data_state']['training_tokens'] == 1228800

def test_architecture_tokenizer_and_context_invariants():
    verification = p.read(p.OUT/'source_verification.json')
    assert p.sha(p.ROOT/'data/tokenizer.json') == p.r.corpus.TOKENIZER_SHA256
    assert verification['effective_context_length'] == 256
    assert verification['architecture_position_capacity'] == 8192
    assert verification['parameter_count'] == 38970880
    old_path = Path(p.read(p.OUT/'rollback_manifest.json')['previous_pointer']['path'])
    for name in ('config.json', 'fermion_config.json'):
        assert p.read(p.RETAINED/name) == p.read(p.SOURCE/name) == p.read(old_path/name)

def test_exposure_counters_not_confused():
    assert p.read(p.OUT/'promotion_manifest.json')['exposure'] == {
        'calibration': 409600, 'long_continuation': 819200, 'total_post_s0': 1228800}

@pytest.mark.parametrize('operation', ['backward', 'optimizer', 'scheduler', 'gguf', 'subprocess', 'evaluate'])
def test_forbidden_runtime_tripwires(operation):
    with p.forbidden_runtime():
        with pytest.raises(RuntimeError):
            if operation == 'backward': p.r.torch.Tensor.backward(None)
            elif operation == 'optimizer': p.r.torch.optim.AdamW.step(None)
            elif operation == 'scheduler': p.r.torch.optim.lr_scheduler.StepLR.step(None)
            elif operation == 'gguf': p.gguf.write_gguf(None, None, None)
            elif operation == 'subprocess': p.subprocess.Popen(['llama-quantize'])
            else: p.r.evaluate(None, None, None)

@pytest.mark.parametrize('relative', ['data/promotion_v4_1_external/normalized/axis_a_functional_user_text.bin',
    'data/promotion_v4_1_external/normalized/axis_b_long_context_narrative.bin',
    'data/promotion_v3_external/test.bin', 'external/wikitext-2/test.txt', 'data/s0_tinystories_test.pt'])
def test_locked_content_denial(relative):
    with p.forbidden_runtime():
        with pytest.raises(PermissionError): (p.ROOT/'tripwire_fixture'/relative).read_bytes()

@pytest.mark.parametrize('path', [p.SOURCE/'model.safetensors', p.ROOT/'exports/FERMiON-CoreLM-S0-F32.gguf',
    p.LINEAGE, p.g.FROZEN/'candidate_manifest.json'])
def test_protected_write_denial(path):
    guard = p.Protection()
    # Call the same path decision used before filesystem mutation; never open the real artifact for writing.
    with pytest.raises(PermissionError): guard.check(path)

def test_atomic_pointer_update(tmp_path):
    pointer = tmp_path/'lineage.json'; old = b'{"current_champion":"old"}\n'
    pointer.write_bytes(old)
    desired = {'current_champion': 'new'}
    seen = []
    p.atomic_pointer_update(pointer, old, desired, lambda value: seen.append(value))
    assert p.read(pointer) == desired and seen == [desired]
    assert not pointer.with_name(pointer.name+'.pending').exists()

def test_pointer_verification_failure_restores_exact_previous_bytes(tmp_path):
    pointer = tmp_path/'lineage.json'; old = b'{ "current_champion": "old" }\r\n'
    pointer.write_bytes(old)
    def failed(_): raise ValueError('verification failure')
    with pytest.raises(ValueError): p.atomic_pointer_update(pointer, old, {'current_champion': 'new'}, failed)
    assert pointer.read_bytes() == old

def test_concurrent_pointer_change_not_overwritten(tmp_path):
    pointer = tmp_path/'lineage.json'; pointer.write_bytes(b'{"other":true}')
    with pytest.raises(RuntimeError): p.atomic_pointer_update(pointer, b'{}', {'new': True}, lambda _: None)
    assert pointer.read_bytes() == b'{"other":true}'

def test_scientific_checkpoints_and_metadata_preserved():
    assert p.metadata() == p.read(p.OUT/'protected_metadata_before.json')
    for path, hashes in p.read(p.OUT/'protected_checkpoint_hashes.json').items():
        assert p.checkpoint_hashes(Path(path)) == hashes

def test_frozen_candidate_manifests_unchanged():
    assert p.sha(p.g.FROZEN/'candidate_manifest.json') == p.g.MANIFEST_HASH
    assert p.sha(p.g.FROZEN/'candidate_completeness.json') == p.g.COMPLETENESS_HASH

def test_gguf_deployment_history_preserved_and_current_reflects_s1_cutover():
    deployment = p.read(p.OUT/'deployment_before.json')
    # Historical 2026-09-15 pre-cutover snapshot is immutable evidence and must not change.
    assert deployment['manifest']['active_champion'] == 'w85@192000'
    # The authorized 2026-09-20 S1 alias cutover intentionally rewrote only these three paths;
    # their current state is verified against production below (see tests/test_s1_deployment_state.py).
    cutover_changed = {'FERMiON-CoreLM-S0-F32.gguf', 'FERMiON-CoreLM-S0-Q8_0.gguf', 'production_manifest.json'}
    for path, digest in deployment['hashes'].items():
        if Path(path).name in cutover_changed:
            continue
        assert p.sha(Path(path)) == digest
    # Current production state reflects the S1 cutover; w85 is retained strictly as rollback.
    current = p.read(p.ROOT/'exports/production_manifest.json')
    assert current['active_champion'] == 's1_long@819200'
    assert current['active_deployed_gguf_lineage'] == 's1_long@819200'
    assert current['rollback']['deployed_gguf_lineage'] == 'w85@192000'
    assert current['active_f32_sha256'] == '5AC11A681A1F721B67512615F9A7B9D6ABFD826F0E47A1BC5893842E38896BFD'
    assert current['active_q8_0_sha256'] == 'B66F14EDEEB64F5B1643800C0A6149FC9BC16F5CF2E3917D36E8720D089F54A1'

def test_pointer_expected_for_phase():
    lineage = p.read(p.LINEAGE)
    if (p.OUT/'lineage_update_receipt.json').exists():
        p.verify_resolves(lineage)
        # Current deployed artifact is S1 after the authorized 2026-09-20 alias cutover;
        # w85 is retained only as the rollback lineage.
        assert lineage['deployed_gguf_artifact']['champion'] == 's1_long@819200'
        assert lineage['deployed_gguf_artifact']['rollback_lineage'] == 'w85@192000'
        assert lineage['champion_pointer_semantics']['current_champion'] == 'canonical_model_champion'
        before = p.read(p.OUT/'lineage_before.json')
        assert lineage['experiments'][:-1] == before['experiments']
        assert {k: v for k, v in lineage.items() if k not in
            ('current_champion', 'experiments', 'deployed_gguf_artifact', 'champion_pointer_semantics')} == {
            k: v for k, v in before.items() if k not in ('current_champion', 'experiments')}
    else:
        assert p.LINEAGE.read_bytes() == (p.OUT/'lineage_before.json').read_bytes()

def test_gate_and_recovery_receipts_unmodified():
    for name, digest in p.read(p.OUT/'gate_receipt.json')['artifacts'].items():
        assert p.sha(p.g.OUT/name) == digest
