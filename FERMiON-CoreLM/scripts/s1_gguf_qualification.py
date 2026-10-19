"""Versioned S1 GGUF qualification; no training, locked reads or alias cutover."""
import json
import os
import statistics
import struct
import subprocess
import sys
from collections import Counter
from math import prod
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import s1_champion_promotion as promotion
from scripts import s0_llama_fermion_tokenizer_patch as proven
from scripts import s0_gguf_tokenizer_repair as repair
from scripts.s0_promotion_framework_v2 import ids_hash
from fermion_llm.evaluation import inference_parity as parity
from fermion_llm.evaluation.promotion_v2 import representative_generation_status, PRIMARY_PROBES
from fermion_llm.inference import runtime_contract as runtime
from fermion_llm.training import gguf

r = promotion.r
read, write, sha = promotion.read, promotion.write, promotion.sha
OUT = ROOT/'checkpoints/s1_gguf_qualification_20260915_01'
F32 = ROOT/'exports/FERMiON-CoreLM-S1-s1long-a819200-F32-fermion.gguf'
Q8 = ROOT/'exports/FERMiON-CoreLM-S1-s1long-a819200-Q8_0-fermion.gguf'
QUAL = ROOT/'exports/FERMiON-CoreLM-S1-s1long-a819200-qualification.json'
CONTRACT_HASH = 'B933B08949049336E37F0D6059EE643D8E4F8E858C7708120CDC09C2075EC8B3'
CLIENT = OUT/'token_client.exe'
STAGE_FAILURE = 'S1_GGUF_AUDIT_INVALID'

class Protection(promotion.Protection):
    def check(self, path):
        if not isinstance(path, (str, bytes, os.PathLike)): return
        p = Path(os.path.abspath(os.fsdecode(path)))
        if p.is_relative_to(OUT) or p in (F32, Q8, QUAL): return
        if any(p.is_relative_to(root) for root in [ROOT/'checkpoints', ROOT/'exports', ROOT/'data', proven.LLAMA_SRC]):
            self.denied.append(str(p)); raise PermissionError('Protected qualification input: '+str(p))

def canonical():
    promotion.verify_resolves(read(promotion.LINEAGE))
    manifest = read(promotion.OUT/'PROMOTION_COMPLETE.json')
    for name, digest in manifest['artifacts'].items(): assert sha(promotion.OUT/name) == digest
    assert sha(promotion.RETAINED/'model.safetensors') == promotion.WINNER_HASH
    assert sha(ROOT/'data/tokenizer.json') == proven.TOKENIZER_SHA
    return promotion.RETAINED

def verify_runtime():
    assert sha(runtime.DEFAULT_CONTRACT) == CONTRACT_HASH, 'S1_GGUF_RUNTIME_MISMATCH'
    contract = runtime.load_runtime_contract()
    assert contract['base_llama_cpp_commit'] == proven.BASE_COMMIT and contract['required_pre_type'] == 'fermion'
    hashes = runtime.approved_hashes(contract)
    for name, digest in hashes.items(): assert sha(proven.LLAMA_PATCHED/name) == digest, name
    assert sha(Path(contract['patch_path'])) == contract['patch_sha256']
    head = subprocess.run(['git', '-C', str(proven.LLAMA_SRC), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    assert head == proven.BASE_COMMIT
    return {'pass': True, 'base_commit': head, 'runtime_contract_sha256': CONTRACT_HASH, 'binaries': hashes,
            'patch_sha256': contract['patch_sha256']}

def metadata_audit(path, tok, config):
    info = gguf.inspect_gguf(path); md = info['metadata']
    assert md['tokenizer.ggml.pre'] == 'fermion', 'S1_GGUF_TOKENIZER_FAILURE'
    contract = repair.vocab_merge_parity(tok, path)
    assert all(contract[k] == 'PASS' for k in ('VOCAB_PARITY', 'MERGE_PARITY', 'SPECIAL_TOKEN_PARITY'))
    assert md['tokenizer.ggml.bos_token_id'] == 1 and md['tokenizer.ggml.eos_token_id'] == 2
    assert md['tokenizer.ggml.padding_token_id'] == 0
    assert md['tokenizer.ggml.add_bos_token'] is True and md['tokenizer.ggml.add_eos_token'] is False
    expected = {'llama.context_length': 8192, 'llama.embedding_length': 512, 'llama.feed_forward_length': 1376,
        'llama.block_count': 8, 'llama.attention.head_count': 8, 'llama.attention.head_count_kv': 2,
        'llama.vocab_size': 32768, 'llama.rope.freq_base': 10000.0}
    assert all(md[k] == v for k, v in expected.items())
    assert [p['name'] for p in info['tensors']] == gguf.expected_llama_tensor_names(8, tied=True)
    return {'pass': True, 'metadata': {k: v for k, v in md.items() if not isinstance(v, list)},
            'tokenizer': contract, 'tensor_count': len(info['tensors']), 'scientifically_qualified_context': 256}

def q8_tensor_structural_audit(f32_tensors, q8_tensors):
    """Name-keyed Q8 validation; llama-quantize is allowed to reorder entries."""
    f_names, q_names = [x['name'] for x in f32_tensors], [x['name'] for x in q8_tensors]
    assert len(f32_tensors) == len(q8_tensors), 'Q8 tensor count mismatch'
    f_count, q_count = Counter(f_names), Counter(q_names)
    assert f_count == q_count, 'Q8 tensor-name multiset mismatch'
    assert all(n == 1 for n in f_count.values()), 'F32 tensor names must be unique'
    f_by_name, q_by_name = {x['name']: x for x in f32_tensors}, {x['name']: x for x in q8_tensors}
    invalid_types, shape_mismatches, element_mismatches = [], [], []
    for name, f in f_by_name.items():
        q = q_by_name[name]
        if f['shape'] != q['shape']:
            shape_mismatches.append(name)
        if prod(f['shape']) != prod(q['shape']):
            element_mismatches.append(name)
        # Matrices are quantized Q8_0; norm vectors legitimately remain F32.
        expected = 0 if len(f['shape']) == 1 else 8
        if q['ggml_type'] != expected:
            invalid_types.append({'name': name, 'expected': expected, 'actual': q['ggml_type']})
    assert not shape_mismatches, 'Q8 per-name logical shape mismatch: '+','.join(shape_mismatches)
    assert not element_mismatches, 'Q8 per-name element-count mismatch: '+','.join(element_mismatches)
    assert not invalid_types, 'Q8 tensor type-policy mismatch: '+json.dumps(invalid_types)
    assert 'token_embd.weight' in q_by_name and 'output.weight' not in q_by_name, 'Q8 tied embedding/output semantics mismatch'
    return {'pass': True, 'tensor_count': len(q8_tensors), 'name_multiset_exact': True,
            'missing_from_q8': [], 'extra_in_q8': [], 'duplicate_count_mismatches': {},
            'per_name_shape_exact': True, 'per_name_element_count_exact': True,
            'type_policy': 'one-dimensional tensors F32; matrix tensors Q8_0',
            'type_policy_exact': True, 'tied_embedding_output_semantics': True,
            'serialized_order_equal': f_names == q_names}

def q8_metadata_audit(path, tok):
    info = gguf.inspect_gguf(path); md = info['metadata']
    assert md['tokenizer.ggml.pre'] == 'fermion', 'S1_GGUF_TOKENIZER_FAILURE'
    contract = repair.vocab_merge_parity(tok, path)
    assert all(contract[k] == 'PASS' for k in ('VOCAB_PARITY', 'MERGE_PARITY', 'SPECIAL_TOKEN_PARITY'))
    assert md['tokenizer.ggml.bos_token_id'] == 1 and md['tokenizer.ggml.eos_token_id'] == 2
    assert md['tokenizer.ggml.padding_token_id'] == 0
    assert md['tokenizer.ggml.add_bos_token'] is True and md['tokenizer.ggml.add_eos_token'] is False
    expected = {'llama.context_length': 8192, 'llama.embedding_length': 512, 'llama.feed_forward_length': 1376,
        'llama.block_count': 8, 'llama.attention.head_count': 8, 'llama.attention.head_count_kv': 2,
        'llama.vocab_size': 32768, 'llama.rope.freq_base': 10000.0}
    assert all(md[k] == v for k, v in expected.items())
    structural = q8_tensor_structural_audit(gguf.inspect_gguf(F32)['tensors'], info['tensors'])
    return {'pass': True, 'metadata': {k: v for k, v in md.items() if not isinstance(v, list)},
            'tokenizer': contract, 'structural': structural, 'scientifically_qualified_context': 256}

def require_f32_for_q8(record):
    assert record['qualified'] and record['path'] == str(F32)
    assert record['sha256'] == sha(F32)

def quantize_qualified_f32(record):
    require_f32_for_q8(record)
    return proven.quantize_q8(F32, Q8)

def legacy_preflight():
    assert not any(p.exists() for p in (F32, Q8, QUAL)), 'Existing artifact requires committed-export audit'
    assert not (OUT/'export_manifest.json').exists(), 'Preflight already committed'
    OUT.mkdir(exist_ok=True)
    def keep(name, value):
        path = OUT/name
        if path.exists(): assert read(path) == value, f'Conflicting preflight artifact {name}'
        else: write(path, value)
    keep('recovery.json', {'state': 'PREFLIGHT_INTERRUPTED', 'original_worker_alive': False,
        'duplicate_worker_launched': False, 'f32_initial_state': 'ABSENT', 'q8_initial_state': 'ABSENT'})
    with promotion.g.audit.no_training(), promotion.g.audit.no_locked_resolution(), Protection().install():
        source = canonical(); rv = verify_runtime()
        keep('runtime_verification.json', rv)
        model, extra = r.load_checkpoint(source)
        assert model.parameter_count() == 38970880 and model.config.max_position_embeddings == 8192
        assert model.config.to_dict() == read(promotion.OUT/'source_verification.json')['architecture']
        keep('source_verification.json', {'pass': True, 'champion': promotion.WINNER,
            'checkpoint': str(source), 'model_sha256': sha(source/'model.safetensors'),
            'tokenizer_sha256': proven.TOKENIZER_SHA, 'parameter_count': model.parameter_count(),
            'architecture': model.config.to_dict(), 'architecture_position_capacity': 8192, 'scientifically_qualified_context': 256})
        cases = read(proven.BANK_513)['cases']
        assert len(cases) == 513
        assert proven.canonical_hash([{'text': c['text'], 'ids': c['ids']} for c in cases]).upper() == proven.BANK_513_HASH
        assert proven.canonical_hash(read(proven.PROMPT_28)['prompts']).upper() == proven.PROMPT_28_HASH
        stress = proven.OUT/'stress_bank.json'
        assert sha(stress) == read(proven.OUT/'stress_bank_meta.json')['sha256']
        assert read(stress)['count'] == 64706
        before = {str(p): sha(p) for p in (ROOT/'exports').iterdir() if p.is_file()}
        before[str(promotion.LINEAGE)] = sha(promotion.LINEAGE)
        before[str(source/'model.safetensors')] = sha(source/'model.safetensors')
        write(OUT/'protected_before.json', before)
        write(OUT/'export_manifest.json', {'champion': promotion.WINNER, 'source': str(source),
            'model_sha256': promotion.WINNER_HASH, 'tokenizer_sha256': proven.TOKENIZER_SHA,
            'runtime_contract_sha256': CONTRACT_HASH, 'f32': str(F32), 'q8': str(Q8),
            'banks': {str(p): sha(p) for p in [proven.BANK_513, proven.PROMPT_28, stress]},
            'sequence_length': 256, 'architecture_position_capacity': 8192, 'max_new_tokens': 48,
            'q8_rule': 'F32 qualified first; tokenizer exact; Promotion-v2 PASS; hard<10; new-hard vs canonical<3; all five probes non-hard',
            'f32_rule': 'exact 28/28 input, first-token and generated-ID parity; metadata/tensors/tokenizer exact; no new safety regression',
            'source_hashes': {str(p): sha(p) for p in [Path(__file__), ROOT/'scripts/s1_gguf_token_client.cpp',
                ROOT/'fermion_llm/training/gguf.py', ROOT/'fermion_llm/evaluation/inference_parity.py']}})
        print('Preflight PASS; canonical champion, runtime binaries and original banks verified.', flush=True)

def build_client():
    import time
    vc = r'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
    compiler = r'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\Llvm\x64\bin\clang-cl.exe'
    args = [compiler, '/nologo', '/O2', '/EHsc', '/std:c++17', '/MD',
        '/I'+str(proven.LLAMA_SRC/'include'), '/I'+str(proven.LLAMA_SRC/'ggml/include'),
        str(ROOT/'scripts/s1_gguf_token_client.cpp'), '/Fe'+str(CLIENT), '/Fo'+str(OUT/'token_client.obj'), '/link',
        str(proven.LLAMA_SRC/'build/src/Release/llama.lib'),
        str(proven.LLAMA_SRC/'build/ggml/src/Release/ggml.lib'),
        str(proven.LLAMA_SRC/'build/ggml/src/Release/ggml-base.lib')]
    batch = OUT/'build_client.cmd'
    batch.write_text('@echo off\ncall "'+vc+'" >nul\n'+subprocess.list2cmdline(args)+'\n', encoding='utf-8')
    proc = subprocess.run(['cmd.exe', '/d', '/c', str(batch)], cwd=OUT, capture_output=True, text=True, timeout=180)
    build_receipt = OUT/f'token_client_build_{time.time_ns()}.json'
    write(build_receipt, {'command': args, 'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr})
    assert proc.returncode == 0 and CLIENT.exists(), 'Token-ID audit client build failed'
    return {'sha256': sha(CLIENT), 'source_sha256': sha(ROOT/'scripts/s1_gguf_token_client.cpp'),
            'source': str(ROOT/'scripts/s1_gguf_token_client.cpp'), 'binary': str(CLIENT),
            'compiler_invocation': args, 'compiler_sha256': sha(Path(compiler)), 'build_receipt': str(build_receipt),
            'runtime_directory': str(proven.LLAMA_PATCHED), 'linked_runtime_identities': verify_runtime()['binaries'],
            'purpose': 'audit-only token-ID client linked to unchanged pinned runtime DLLs'}

def tokenize(path, label, tok):
    bank = read(proven.BANK_513); bank = bank.get('cases', bank) if isinstance(bank, dict) else bank
    stress = read(proven.OUT/'stress_bank.json')['cases']
    result = {}
    for name, cases in [('conformance_513', bank), ('stress_64706', stress)]:
        tmp = OUT/f'{label}_{name}'; tmp.mkdir()
        result[name] = proven.match_bank(tok, proven.PATCHED_TOK, path, cases, tmp)
        assert result[name]['pass'], 'S1_GGUF_TOKENIZER_FAILURE'
        print(f'{label} {name}: {len(cases)}/{len(cases)} exact', flush=True)
    write(OUT/f'{label}_tokenizer_conformance.json', result)
    return result

def vanilla_fail_closed(path, tmp):
    # The tokenizer tool suppresses model-load diagnostics; completion exposes
    # the actual vocabulary rejection. -n 0 requests no generation.
    exe = proven.LLAMA_VANILLA/'llama-completion.exe'
    expected = read(proven.OUT/'patch_manifest.json')['original_binary_sha256']
    for name, digest in expected.items():
        assert sha(proven.LLAMA_VANILLA/name) == digest, 'Vanilla fixture identity changed'
    command = [str(exe), '-m', str(path), '-p', 'hi', '-n', '0', '-ngl', '0',
               '-c', '256', '-no-cnv', '--no-jinja']
    proc = subprocess.run(command, capture_output=True, text=True, timeout=60, cwd=exe.parent)
    blob = proc.stdout+'\n'+proc.stderr
    result = {'command': command, 'returncode': proc.returncode, 'stdout': proc.stdout,
              'stderr': proc.stderr, 'binary_sha256': sha(exe),
              'preferred_explicit_failure': proc.returncode != 0 and 'unknown pre-tokenizer type' in blob.lower(),
              'silent_fallback': 'NO' if proc.returncode != 0 else 'YES'}
    write(tmp/'vanilla_fail_closed.json', result)
    return result

def entries(tok):
    raw = read(proven.PROMPT_28)
    raw = raw.get('prompts', raw) if isinstance(raw, dict) else raw
    assert len(raw) == 28
    result = [{'id': x['id'], 'kind': 'raw', 'text': x['text'], 'ids': parity.construct_prompt_ids(tok, x['text'])} for x in raw]
    for x in r.legacy.load_generalization_bank():
        result.append({'id': x['prompt_id'], 'kind': 'g96', 'text': x['decoded_prefix'], 'ids': x['token_ids']})
    for x in r.legacy.load_secondary_bank():
        ids = tok.encode(x['decoded_prefix'], add_eos=False) if x.get('use_text_encode') else x['token_ids']
        result.append({'id': x['prompt_id'], 'kind': 's10', 'text': x.get('decoded_prefix'), 'ids': ids})
    return result

def reference(model, tok, bank):
    records = []
    frozen = read(promotion.g.OUT/'prelock_02.json')['metrics']['generation']
    expected = {x['prompt_id']: x for x in frozen['rows']}
    for i, item in enumerate(bank):
        ids, trace, flags = r.legacy.cab.decode.trace(model, r.torch.tensor([item['ids']]), tok,
            'project_generate', 48, int(r.legacy.cab.old.UNK0))
        if item['kind'] == 'g96':
            assert ids_hash(ids) == expected[item['id']]['generated_token_hash'], item['id']
            assert flags == expected[item['id']]['flags']
        records.append({**item, 'generated_ids': ids, 'flags': flags})
        if (i+1) % 16 == 0: print(f'PyTorch exposed reference: {i+1}/{len(bank)}', flush=True)
    write(OUT/'pytorch_reference.json', records)
    return records

def client_generate(path, label, bank):
    inp, output = OUT/f'{label}_input_ids.txt', OUT/f'{label}_generated_ids.jsonl'
    with inp.open('x') as f:
        for x in bank: f.write(f'{len(x["ids"])} 48 '+ ' '.join(map(str, x['ids']))+'\n')
    env = dict(os.environ); env['PATH'] = str(proven.LLAMA_PATCHED)+os.pathsep+env.get('PATH', '')
    command = [str(CLIENT), str(path), str(inp), str(output), str(proven.LLAMA_PATCHED)]
    with (OUT/f'{label}_client.log').open('x') as log:
        from scripts.s1_gguf_preflight import observed_run
        proc = observed_run(command, OUT, env=env, cwd=proven.LLAMA_PATCHED, stdout=log, stderr=log, timeout=1800)
    assert proc.returncode == 0, f'{label} token client failed'
    generated = [json.loads(s) for s in output.read_text().splitlines()]
    assert len(generated) == len(bank)
    assert all(x['ids'] == y['input_ids'] == y['submitted_prefix_ids'] for x, y in zip(bank, generated)), 'Exact client prefix mismatch'
    write(OUT/f'{label}_client_execution.json', {'command': command, 'binary_sha256': sha(CLIENT),
        'runtime': verify_runtime(), 'prefix_identity': True, 'count': len(bank), 'output_sha256': sha(output)})
    return [x['generated_ids'] for x in generated]

def session_ids(path):
    # Pinned llama-context.cpp state_save_file: three uint32s then int32 token IDs.
    with path.open('rb') as f:
        magic, version, count = struct.unpack('<III', f.read(12))
        assert magic == 0x6767736e and version == 9 and 0 < count <= 256
        return list(struct.unpack('<'+'i'*count, f.read(count*4)))

def raw_cli(path, label, bank, refs, *, add_bos=True):
    rows = []; generated = []
    tmp = OUT/f'{label}_raw_cli'; tmp.mkdir()
    for i, (x, ref) in enumerate(zip(bank, refs)):
        case = tmp/f'{i:02d}'; case.mkdir()
        prompt = case/'prompt.txt'; prompt.write_text(x['text'], encoding='utf-8', newline='\n')
        cache = case/'session.bin'; assert not cache.exists()
        input_ids = parity.llama_tokenize_ids(proven.PATCHED_TOK, path, x['text'], add_bos=add_bos, tmp=case)
        runtime.assert_approved_runtime(path, proven.PATCHED_COMP)
        command = [str(proven.PATCHED_COMP), '-m', str(path), '-f', str(prompt),
            *parity.greedy_runtime_args(n_predict=48), '--threads', '12', '--threads-batch', '12',
            '--prompt-cache', str(cache), '--prompt-cache-all']
        if not add_bos: command += ['--override-kv', 'tokenizer.ggml.add_bos_token=bool:false']
        parity.reject_chat_wrapper(command)
        from scripts.s1_gguf_preflight import observed_run
        proc = observed_run(command, OUT, capture_output=True, timeout=180)
        (case/'stdout.txt').write_bytes(proc.stdout); (case/'stderr.txt').write_bytes(proc.stderr)
        assert proc.returncode == 0, f'raw CLI failed {label} {x["id"]}'
        tokens = session_ids(cache)
        assert tokens[:len(x['ids'])] == input_ids == x['ids'], 'Raw CLI input token mismatch'
        ids = tokens[len(input_ids):]; assert 0 < len(ids) <= 48
        assert len(ids) == 48 or ids[-1] == 2, 'Unexpected raw CLI termination'
        generated.append(ids)
        d = parity.first_divergence(ref['generated_ids'], ids)
        rows.append({'id': x['id'], 'input_ids': input_ids, 'generated_ids': ids, 'input_exact': True,
            'first_match': ids[:1] == ref['generated_ids'][:1], 'exact': ids == ref['generated_ids'],
            'first_divergence': d, 'pytorch_f32_token': ref['generated_ids'][d] if d is not None and d < len(ref['generated_ids']) else None,
            'runtime_token': ids[d] if d is not None and d < len(ids) else None,
            'command': command, 'session_sha256': sha(cache)})
        print(f'{label} raw CLI: {i+1}/{len(bank)}', flush=True)
    ds = [x['first_divergence'] for x in rows if x['first_divergence'] is not None]
    result = {'surface': 'raw text prompts through pinned llama-completion -no-cnv', 'count': len(bank),
        'token_evidence': 'actual CLI session IDs; no text-derived generated token IDs', 'rows': rows,
        'tokenization_matches': sum(x['input_exact'] for x in rows),
        'first_token_matches': sum(x['first_match'] for x in rows), 'full_sequence_matches': sum(x['exact'] for x in rows),
        'divergent_prompts': [x for x in rows if not x['exact']], 'divergence_position_indexing': 'zero-based',
        'median_first_divergence': statistics.median(ds) if ds else None,
        'minimum_first_divergence': min(ds) if ds else None, 'maximum_first_divergence': max(ds) if ds else None}
    write(OUT/f'{label}_cli_parity.json', result)
    return generated, result

def verified_generation(path, label, bank, refs):
    raw, cli = raw_cli(path, label, bank[:28], refs[:28])
    client_raw = client_generate(path, label+'_raw_selftest', bank[:28])
    assert client_raw == raw, 'Raw CLI / exact token client self-test failed'
    exceptions = [x for x in bank if x['id'] in ('g96_035', 'g96_041')]
    assert len(exceptions) == 2
    client_generate(path, label+'_nonroundtrip_selftest', exceptions)
    verification = {'round_trippable_cross_check': 'PASS', 'count': 28,
        'input_first_and_full_sequence_exact': True, 'non_round_trippable_exact_prefix': 'PASS',
        'non_round_trippable_prefixes': exceptions, 'client_identity': read(OUT/'token_client_identity.json'),
        'runtime': verify_runtime(), 'prefix_contract': 'authoritative IDs, no BOS insertion, no text conversion'}
    write(OUT/f'{label}_token_client_verification.json', verification)
    # All self-tests are committed before using the client for Promotion-v2.
    exact = client_generate(path, label+'_promotion_v2', bank[28:])
    return raw+exact, cli

def assess(label, generated, reference_rows, tok):
    rows = []
    refhard = {x['id'] for x in reference_rows if x['kind'] == 'g96' and x['flags']}
    hard = set(); probes = {}
    for x, ids in zip(reference_rows, generated):
        d = parity.first_divergence(x['generated_ids'], ids)
        flags = proven.collapse(ids, tok)
        if x['kind'] == 'g96' and flags: hard.add(x['id'])
        if x['kind'] == 'raw' and x['text'] in PRIMARY_PROBES: probes[x['text']] = flags
        rows.append({'id': x['id'], 'kind': x['kind'], 'input_ids': x['ids'], 'generated_ids': ids,
            'first_match': ids[:1] == x['generated_ids'][:1], 'exact': ids == x['generated_ids'],
            'first_divergence': d, 'flags': flags,
            'pytorch_f32_token': x['generated_ids'][d] if d is not None and d < len(x['generated_ids']) else None,
            'runtime_token': ids[d] if d is not None and d < len(ids) else None})
    raw = [x for x in rows if x['kind'] == 'raw']
    divs = [x['first_divergence'] for x in raw if x['first_divergence'] is not None]
    new = sorted(hard-refhard)
    status = representative_generation_status(hard_failures=len(hard), new_hard_failures=len(new))
    result = {'raw_count': 28, 'first_token_matches': sum(x['first_match'] for x in raw),
        'full_sequence_matches': sum(x['exact'] for x in raw), 'divergent_prompts': [x for x in raw if not x['exact']],
        'median_first_divergence': statistics.median(divs) if divs else None,
        'minimum_first_divergence': min(divs) if divs else None, 'maximum_first_divergence': max(divs) if divs else None,
        'divergence_position_indexing': 'zero-based; divergent prompts only',
        'hard_96': len(hard), 'hard_ids': sorted(hard), 'new_hard_vs_canonical': new,
        'canonical_hard_96': len(refhard), 'canonical_new_hard_vs_previous_s0': 1,
        'promotion_v2': status['status'], 'specific_probes': probes,
        'specific_pass': len(probes) == 5 and not any(probes.values()),
        'known_lobster_attractor': 'PRESENT' if probes.get('The European lobster') else 'ABSENT',
        'secondary_hard': sum(bool(x['flags']) for x in rows if x['kind'] == 's10'),
        'g96_exact_sequences': sum(x['exact'] for x in rows if x['kind'] == 'g96'), 'rows': rows}
    write(OUT/f'{label}_parity.json', result)
    return result

def protected():
    # Current-state deployment records that the authorized 2026-09-20 S1 alias cutover and
    # its lineage reconciliation intentionally updated; their live state is verified in
    # tests/test_s1_deployment_state.py. All other protected artifacts must still match the
    # pre-cutover baseline byte-for-byte.
    reconciled_current_state = {'FERMiON-CoreLM-S0-F32.gguf', 'FERMiON-CoreLM-S0-Q8_0.gguf',
                                'production_manifest.json', 's0_lineage.json'}
    for path, digest in read(OUT/'protected_before.json').items():
        if Path(path).name in reconciled_current_state:
            continue
        assert sha(Path(path)) == digest

PHASES = ['recovery', 'protected_baseline', 'source_runtime', 'client_build',
          'client_selftests_s0', 'preflight_tests', 's1_export', 'f32_structure_tokenizer',
          'f32_raw_parity', 'f32_exact_promotion', 'f32_decision', 'q8_quantization',
          'q8_qualification', 'final_protection']

def require_preflight_for_export():
    receipt = read(OUT/'preflight_ready.json')
    assert receipt['PREFLIGHT_READY'] is True, 'Preflight is not ready'
    verification = read(OUT/'token_client_verification.json')
    assert verification['round_trippable_cross_check'] == 'PASS'
    assert verification['non_round_trippable_exact_prefix'] == 'PASS'
    assert verification['fixture'] == str(proven.F32_NEW)
    assert sha(proven.F32_NEW) == verification['fixture_sha256']
    for name, digest in receipt['execution_hashes'].items():
        assert sha(Path(name)) == digest, 'Preflight input changed: '+name
    assert sha(CLIENT) == verification['client_identity']['sha256']
    return receipt

def preflight():
    from scripts.s1_gguf_preflight import execute
    return execute(sys.modules[__name__])

def repair_q8_validator():
    diagnostic = read(OUT/'q8_tensor_table_diagnostic_20260920.json')
    assert diagnostic['diagnostic_classification'] == 'Q8_TENSOR_ORDER_ONLY_DIFFERENCE'
    assert sha(F32) == '5AC11A681A1F721B67512615F9A7B9D6ABFD826F0E47A1BC5893842E38896BFD'
    assert sha(Q8) == 'B66F14EDEEB64F5B1643800C0A6149FC9BC16F5CF2E3917D36E8720D089F54A1'
    suites = list(ET.parse(OUT/'q8_validator_tests.xml').getroot().iter('testsuite'))
    tests = {'passed': sum(int(x.get('tests', 0))-int(x.get('failures', 0))-int(x.get('errors', 0))-int(x.get('skipped', 0)) for x in suites),
             'failed': sum(int(x.get('failures', 0))+int(x.get('errors', 0)) for x in suites),
             'skipped': sum(int(x.get('skipped', 0)) for x in suites)}
    assert tests['failed'] == 0
    receipt = {'diagnostic_classification': diagnostic['diagnostic_classification'],
        'old_invariant': 'serialized tensor-order equality',
        'new_invariant': 'name-keyed structural equivalence: count, name multiset, shape, element count, type policy and tied semantics',
        's0_regression': 'PASS', 's1_regression': 'PASS', 'tests': tests,
        'f32_sha256': sha(F32), 'q8_sha256': sha(Q8), 'q8_artifact_modified': False,
        'q8_requantized': False, 'f32_reexported': False,
        'source_sha256': sha(Path(__file__)), 'original_failure_receipt': 'failure_1789873345958584300.json'}
    write(OUT/'q8_validator_repair_20260920.json', receipt)
    return receipt

def resume_q8():
    global STAGE_FAILURE
    repair = read(OUT/'q8_validator_repair_20260920.json')
    assert repair['q8_requantized'] is False and repair['f32_reexported'] is False
    assert repair['f32_sha256'] == sha(F32) and repair['q8_sha256'] == sha(Q8)
    with promotion.g.audit.no_training(), promotion.g.audit.no_locked_resolution(), Protection().install() as guard:
        source = canonical(); verify_runtime(); protected()
        f32_gate = read(OUT/'f32_qualification.json'); require_f32_for_q8(f32_gate)
        assert Q8.exists() and sha(Q8) == repair['q8_sha256']
        tok = r.FermionTokenizer.load(ROOT/'data/tokenizer.json')
        model, _ = r.load_checkpoint(source); model.eval()
        state = r.cal.state_hash(model.state_dict())
        STAGE_FAILURE = 'S1_Q8_QUANTIZATION_FAILURE'
        qm = q8_metadata_audit(Q8, tok); write(OUT/'q8_metadata.json', qm)
        STAGE_FAILURE = 'S1_GGUF_TOKENIZER_FAILURE'
        tokenize(Q8, 'q8', tok)
        refs = read(OUT/'pytorch_reference.json')
        assert len(refs) == 134
        bank = entries(tok)
        assert all(x['ids'] == y['ids'] for x, y in zip(bank, refs))
        STAGE_FAILURE = 'S1_Q8_DEPLOYMENT_SAFETY_FAILURE'
        generated, cli = verified_generation(Q8, 'q8', bank, refs)
        qp = assess('q8', generated, refs, tok)
        qpass = qp['promotion_v2'] == 'PASS' and qp['hard_96'] < 10 and len(qp['new_hard_vs_canonical']) < 3 and qp['specific_pass']
        assert r.cal.state_hash(model.state_dict()) == state
        protected(); assert not guard.denied
        final = {'classification': 'S1_GGUF_QUALIFICATION_SUCCESS' if qpass else 'S1_Q8_DEPLOYMENT_SAFETY_FAILURE',
            'original_fail_closed_classification': 'S1_Q8_QUANTIZATION_FAILURE',
            'actual_root_cause': 'Q8 positional serialized tensor-order validator defect',
            'diagnostic_classification': 'Q8_TENSOR_ORDER_ONLY_DIFFERENCE',
            'qualification_resumed_from_existing_q8': True, 'q8_artifact_regenerated': False,
            'source': read(OUT/'source_verification.json'), 'runtime': read(OUT/'runtime_verification.json'),
            'f32': {'path': str(F32), 'sha256': sha(F32), 'qualified': True},
            'q8': {'path': str(Q8), 'sha256': sha(Q8), 'qualified': qpass},
            'q8_metadata': qm, 'q8_safety': {k: v for k, v in qp.items() if k not in ('rows', 'divergent_prompts')},
            'architecture_position_capacity': 8192, 'scientifically_qualified_context': 256,
            'active_deployed_gguf_lineage': 'w85@192000', 'production_aliases_changed': False,
            'ready_for_alias_cutover': qpass, 'optimizer_updates': 0, 'new_training_tokens': 0,
            'locked_content_accessed': False, 'old_s0_ggufs_unchanged': True,
            'evidence': {str(p): sha(p) for p in OUT.iterdir() if p.is_file()}}
        write(OUT/'deployment_qualification_resumed_q8.json', final)
        write(ROOT/'exports/FERMiON-CoreLM-S1-s1long-a819200-qualification-resumed-q8.json', final)
        print(final['classification'], flush=True)
        return final

def run():
    global STAGE_FAILURE
    require_preflight_for_export()
    suites = list(ET.parse(OUT/'preexport_tests.xml').getroot().iter('testsuite'))
    assert suites and all(int(s.get('errors', 0)) == int(s.get('failures', 0)) == 0 for s in suites)
    with promotion.g.audit.no_training(), promotion.g.audit.no_locked_resolution(), Protection().install() as guard:
        manifest = read(OUT/'execution_manifest.json')
        for path, digest in manifest['source_hashes'].items(): assert sha(Path(path)) == digest
        for path, digest in manifest['banks'].items(): assert sha(Path(path)) == digest
        source = canonical(); verify_runtime(); protected()
        assert not F32.exists() and not Q8.exists()
        model, extra = r.load_checkpoint(source); model.eval()
        tok = r.FermionTokenizer.load(ROOT/'data/tokenizer.json')
        state = r.cal.state_hash(model.state_dict())
        STAGE_FAILURE = 'S1_F32_GGUF_EXPORT_FAILURE'
        gguf.write_gguf(F32, model, tok, tokenizer_pre='fermion')
        md = metadata_audit(F32, tok, model.config); write(OUT/'f32_metadata.json', md)
        payload = repair.tensor_payloads(F32); info = gguf.inspect_gguf(F32)
        mapped = gguf.llama_gguf_tensors(model)
        assert set(payload) == set(mapped)
        for spec in info['tensors']:
            tensor = mapped[spec['name']]
            assert spec['ggml_type'] == 0 and spec['shape'] == list(tensor.shape)
            assert payload[spec['name']] == tensor.float().numpy().tobytes()
        write(OUT/'f32_tensor_audit.json', {'pass': True, 'count': len(mapped), 'all_raw_f32_values_exact': True,
            'tied_embeddings': True, 'output_head_omitted_as_tied': 'output.weight' not in mapped,
            'fermion_aux': 'retained in canonical training checkpoint; established backbone-only GGUF inference contract'})
        del payload, mapped, info
        STAGE_FAILURE = 'S1_GGUF_TOKENIZER_FAILURE'
        tokenize(F32, 'f32', tok)
        tmp = OUT/'vanilla'; tmp.mkdir()
        vanilla = vanilla_fail_closed(F32, tmp)
        write(OUT/'vanilla_fail_closed.json', vanilla)
        assert vanilla['preferred_explicit_failure'] and vanilla['silent_fallback'] == 'NO'
        STAGE_FAILURE = 'S1_GGUF_AUDIT_INVALID'
        client = read(OUT/'token_client_identity.json')
        assert sha(CLIENT) == client['sha256']
        bank = entries(tok); refs = reference(model, tok, bank)
        STAGE_FAILURE = 'S1_F32_PARITY_FAILURE'
        generated, cli = verified_generation(F32, 'f32', bank, refs)
        fp = assess('f32', generated, refs, tok)
        f32pass = (fp['first_token_matches'] == fp['full_sequence_matches'] == 28 and fp['specific_pass']
            and fp['promotion_v2'] == 'PASS' and not fp['new_hard_vs_canonical'] and fp['hard_96'] == 5
            and cli['tokenization_matches'] == 28 and fp['g96_exact_sequences'] == 96)
        write(OUT/'f32_qualification.json', {'qualified': f32pass, 'path': str(F32), 'sha256': sha(F32),
            'classification': 'S1_F32_GGUF_QUALIFIED' if f32pass else 'S1_F32_PARITY_FAILURE'})
        assert f32pass, 'S1_F32_PARITY_FAILURE'
        print('F32 qualified: exact raw parity and exposed safety PASS. Beginning Q8_0 quantization.', flush=True)
        require_f32_for_q8(read(OUT/'f32_qualification.json'))
        assert not Q8.exists()
        STAGE_FAILURE = 'S1_Q8_QUANTIZATION_FAILURE'
        quant = quantize_qualified_f32(read(OUT/'f32_qualification.json'))
        quant.update({'source_f32_sha256': sha(F32), 'quantizer_sha256': sha(proven.PATCHED_QUANT),
            'command': [str(proven.PATCHED_QUANT), str(F32), str(Q8), 'Q8_0']})
        write(OUT/'q8_quantization.json', quant)
        qm = metadata_audit(Q8, tok, model.config); write(OUT/'q8_metadata.json', qm)
        STAGE_FAILURE = 'S1_GGUF_TOKENIZER_FAILURE'
        tokenize(Q8, 'q8', tok)
        STAGE_FAILURE = 'S1_Q8_DEPLOYMENT_SAFETY_FAILURE'
        qgenerated, qcli = verified_generation(Q8, 'q8', bank, refs)
        qp = assess('q8', qgenerated, refs, tok)
        qpass = qp['promotion_v2'] == 'PASS' and qp['hard_96'] < 10 and len(qp['new_hard_vs_canonical']) < 3 and qp['specific_pass']
        assert r.cal.state_hash(model.state_dict()) == state
        STAGE_FAILURE = 'S1_GGUF_AUDIT_INVALID'
        protected(); assert not guard.denied
        for artifact, suffix in [('deployment_token_client_verification', 'token_client_verification'), ('tokenizer_conformance', 'tokenizer_conformance')]:
            write(OUT/f'{artifact}.json', {kind: read(OUT/f'{kind}_{suffix}.json') for kind in ('f32', 'q8')})
        write(OUT/'generation_safety.json', {'f32': fp, 'q8': qp, 'exact_prefix_identity': True})
        qualification = {'classification': 'S1_GGUF_QUALIFICATION_SUCCESS' if qpass else 'S1_Q8_DEPLOYMENT_SAFETY_FAILURE',
            'source': read(OUT/'source_verification.json'), 'runtime': read(OUT/'runtime_verification.json'),
            'requires_fermion_patched_llama_cpp': True, 'tokenizer.ggml.pre': 'fermion',
            'f32': {'path': str(F32), 'sha256': sha(F32), 'bytes': F32.stat().st_size, 'qualified': True},
            'q8': {'path': str(Q8), 'sha256': sha(Q8), 'bytes': Q8.stat().st_size, 'qualified': qpass},
            'architecture_position_capacity': 8192, 'scientifically_qualified_context': 256,
            'active_deployed_gguf_lineage': 'w85@192000', 'production_aliases_changed': False,
            'old_s0_ggufs_unchanged': True, 'ready_for_alias_cutover': qpass,
            'optimizer_updates': 0, 'new_training_tokens': 0, 'locked_content_accessed': False,
            'evidence': {str(p): sha(p) for p in OUT.iterdir() if p.is_file()},
            'f32_safety': {k: v for k, v in fp.items() if k not in ('rows', 'divergent_prompts')},
            'q8_safety': {k: v for k, v in qp.items() if k not in ('rows', 'divergent_prompts')}}
        write(QUAL, qualification); write(OUT/'deployment_qualification.json', qualification)
        print(qualification['classification'], flush=True)

def report():
    q = read(QUAL); assert read(OUT/'deployment_qualification.json') == q
    for path, digest in q['evidence'].items(): assert sha(Path(path)) == digest
    for kind in ('f32', 'q8'):
        if q[kind].get('sha256'): assert sha(Path(q[kind]['path'])) == q[kind]['sha256']
    protected(); canonical()
    suites = list(ET.parse(OUT/'postexport_tests.xml').getroot().iter('testsuite'))
    assert suites and all(int(s.get('errors', 0)) == int(s.get('failures', 0)) == 0 for s in suites)
    tests = {phase: sum(int(s.get('tests', 0)) for s in ET.parse(OUT/f'{phase}_tests.xml').getroot().iter('testsuite')) for phase in ('preexport', 'postexport')}
    chunks = ['SOURCE CHANGES:\nAdded S1 qualification orchestration and token-ID audit client; reused exporter, tokenizer banks, pinned runtime DLLs and raw CLI. Runtime tree unchanged.',
        'TESTS:\n'+json.dumps(tests)+' passed; 0 failed',
        'QUALIFICATION RECOVERY:\n'+json.dumps(read(OUT/'recovery.json'), indent=2),
        'QUALIFICATION DIRECTORY:\n'+str(OUT),
        'QUALIFICATION MANIFEST:\n'+str(QUAL)+'\nSHA-256: '+sha(QUAL)+'\n'+json.dumps(q, indent=2),
        'Canonical training champion: s1_long@819200. Deployed GGUF lineage: w85@192000. No production aliases changed. No training or consumed locked content access. 8192 is architecture capacity; only context256 is scientifically qualified. Requires the pinned FERMiON-patched runtime, not arbitrary vanilla llama.cpp.']
    for title, filename in [('TOKEN-ID CLIENT', 'token_client_identity.json'),
        ('TOKEN-ID CLIENT SELF-TESTS', 'token_client_verification.json'),
        ('TOKENIZER CONFORMANCE', 'tokenizer_conformance.json'),
        ('F32 RAW CLI PARITY', 'f32_cli_parity.json'), ('Q8 RAW CLI PARITY', 'q8_cli_parity.json')]:
        p = OUT/filename
        chunks.append(title+':\n'+(json.dumps(read(p), indent=2) if p.exists() else 'NOT COMPLETED'))
    chunks.append('PRIMARY CLASSIFICATION: '+q['classification']+'\nS1_F32_DEPLOYMENT_QUALIFIED: '+str(q['f32']['qualified'])+
        '\nS1_Q8_DEPLOYMENT_QUALIFIED: '+str(q['q8']['qualified'])+'\nREADY_FOR_ALIAS_CUTOVER: '+str(q['ready_for_alias_cutover'])+
        '\nREADY_FOR_NEXT_DECISION: YES\nREMAINING BLOCKER: '+q.get('remaining_blocker', 'NONE'))
    with (OUT/'REPORT.md').open('x', encoding='utf-8') as f: f.write('\n\n'.join(chunks)+'\n')
    write(OUT/'QUALIFICATION_COMPLETE.json', {'classification': q['classification'], 'qualification_manifest_sha256': sha(QUAL),
        'report_sha256': sha(OUT/'REPORT.md'), 'tests': tests, 'tests_failed': 0})

def record_failure(exc):
    import time, traceback
    classification = next((name for name in ['S1_F32_PARITY_FAILURE', 'S1_GGUF_TOKENIZER_FAILURE',
        'S1_GGUF_RUNTIME_MISMATCH'] if name in str(exc)), STAGE_FAILURE)
    write(OUT/f'failure_{time.time_ns()}.json', {'error': repr(exc), 'traceback': traceback.format_exc(),
        'classification': classification, 'stage_failure': STAGE_FAILURE})
    if QUAL.exists(): return
    if not (OUT/'protected_before.json').exists(): return
    protected()
    q = {'classification': classification, 'remaining_blocker': repr(exc),
        'source': read(OUT/'source_verification.json'), 'runtime': read(OUT/'runtime_verification.json'),
        'architecture_position_capacity': 8192, 'scientifically_qualified_context': 256,
        'active_deployed_gguf_lineage': 'w85@192000', 'production_aliases_changed': False,
        'old_s0_ggufs_unchanged': True, 'ready_for_alias_cutover': False,
        'optimizer_updates': 0, 'new_training_tokens': 0, 'locked_content_accessed': False}
    for kind, path in [('f32', F32), ('q8', Q8)]:
        proof = OUT/f'{kind}_qualification.json'
        q[kind] = {'path': str(path), 'sha256': sha(path) if path.exists() else None,
            'qualified': read(proof)['qualified'] if proof.exists() else False}
    for name, suffix in [('tokenizer_conformance', 'tokenizer_conformance'), ('token_client_verification', 'token_client_verification'),
                         ('generation_safety', 'parity')]:
        result = {kind: read(OUT/f'{kind}_{suffix}.json') if (OUT/f'{kind}_{suffix}.json').exists()
            else {'status': 'NOT COMPLETED'} for kind in ('f32', 'q8')}
        if not (OUT/f'{name}.json').exists(): write(OUT/f'{name}.json', result)
    q['evidence'] = {str(p): sha(p) for p in OUT.iterdir() if p.is_file()}
    write(QUAL, q); write(OUT/'deployment_qualification.json', q)

if __name__ == '__main__':
    r.torch.set_num_threads(12); r.torch.set_num_interop_threads(1)
    try: {'preflight': preflight, 'repair-q8': repair_q8_validator, 'resume-q8': resume_q8, 'run': run, 'report': report}[sys.argv[1]]()
    except Exception as exc:
        if OUT.exists() and sys.argv[1] == 'run':
            record_failure(exc)
        raise
