"""Fixed, bounded S1 mixture calibration contracts; no promotion evaluation."""
from __future__ import annotations
import hashlib
import json
import math
import os
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import torch
from fermion_llm.data import s1_r2 as r2, s1_corpus as corpus

BUCKETS = r2.BUCKETS
COUNTS = {
    's1_25': dict(zip((*BUCKETS, 'wiki', 'tiny'), (60, 60, 40, 40, 510, 90))),
    's1_50': dict(zip((*BUCKETS, 'wiki', 'tiny'), (120, 120, 80, 80, 340, 60))),
    's1_75': dict(zip((*BUCKETS, 'wiki', 'tiny'), (180, 180, 120, 120, 170, 30))),
}
EVAL_GRID = (0, 102400, 204800, 307200, 409600)
GEN_GRID = (0, 204800, 409600)
CORPUS_HASH = '6252D1320B68097107B5CBD9307839008F3BF2D134CA22F26ED03440F9842B93'
POLICY = '63365590c8b94f55b50b6896ee7c9bddcfc25afb49482c0b9619088b0da639ef'

def dev_key(row):
    # R2's authoritative document_id is the s1_document_id in this role protocol.
    return hashlib.sha256(('S1_DEV_V1' + row['bucket'] + row['document_id'] + row['normalized_content_sha256']).encode()).hexdigest()

def split_roles(rows):
    dev, train, stats = [], [], {}
    for bucket in BUCKETS:
        ordered = sorted((r for r in rows if r['bucket'] == bucket), key=lambda r: (dev_key(r), r['document_id']))
        selected, tokens = [], 0
        minimum = 4 if bucket == corpus.BUCKET_NARRATIVE else 128
        while len(selected) < minimum or tokens < 128000:
            if len(selected) == len(ordered):
                raise ValueError('S1_CALIBRATION_DATA_SPLIT_FAILURE: insufficient development pool')
            row = ordered[len(selected)]
            selected.append(row)
            tokens += row['valid_target_tokens']
        dev.extend(selected)
        train.extend(ordered[len(selected):])
        stats[bucket] = {'documents': len(selected), 'held_out_valid_tokens': tokens}
    if {r['document_id'] for r in dev} & {r['document_id'] for r in train}:
        raise ValueError('development/train overlap')
    return dev, train, stats

def schedules():
    result = {}
    for cell, counts in COUNTS.items():
        items = [(hashlib.sha256(f'S1_CAL_V1:{cell}:{source}:{i}'.encode()).hexdigest(), source)
                 for source, count in counts.items() for i in range(count)]
        result[cell] = [s for _, s in sorted(items)]
        if Counter(result[cell]) != counts or len(result[cell]) != 800:
            raise ValueError('source schedule mismatch')
    return result

class ExactStream:
    """Consume each causal target once; retain row context when a budget splits it."""
    def __init__(self, rows, pad_id=0, *, row=0, position=1, cycle=False):
        self.rows, self.pad_id, self.row, self.position, self.cycle = rows, pad_id, row, position, cycle

    def state(self):
        return {'row': self.row, 'position': self.position}

    def take(self, count):
        inputs, labels = [], []
        while count:
            if not self.cycle and self.row >= len(self.rows):
                raise ValueError('insufficient usable target tokens')
            row = list(self.rows[self.row % len(self.rows)])
            if len(row) != 256:
                raise ValueError('context must remain 256')
            available = [i for i in range(self.position, 256) if row[i] != self.pad_id]
            if not available:
                self.row += 1
                self.position = 1
                continue
            chosen = available[:count]
            mask = [-100] * 256
            for i in chosen:
                mask[i] = row[i]
            inputs.append(row)
            labels.append(mask)
            count -= len(chosen)
            self.position = chosen[-1] + 1
            if len(chosen) == len(available):
                self.row += 1
                self.position = 1
        x, y = torch.tensor(inputs), torch.tensor(labels)
        return x, y

def forbidden_path(path):
    try:
        p = os.fsdecode(path).replace('\\', '/').lower()
    except TypeError:
        return False
    return any(s in p for s in (
        '/data/promotion_v3_external/', '/data/promotion_v4_1_external/',
        '/data/promotion_v4_external/', '/external/wikitext-2/test.txt',
        '/s0_tinystories_test', '/tinystories-test',
        '/s0_locked_promotion_gate', '/s0_promotion_protocol_v3_1_20260911_01/holdout',
    ))

# Locked-data enforcement is process-global (sys.addaudithook cannot be removed) but
# reference-counted: the audit hook is installed at most once and only *enforces* while
# the activation depth is positive. install_access_guard() activates (+1) and never
# needs a release, so real calibration/promotion runs that call it directly stay guarded
# for the rest of the process exactly as before. Scoped callers pair it with
# release_access_guard() (or use guarded_access()) so enforcement does not leak into
# later, unrelated code (e.g. other tests in the same process).
_GUARD_HOOK_INSTALLED = False
_GUARD_DEPTH = 0


def guard_is_active():
    return _GUARD_DEPTH > 0


def _ensure_access_hook():
    global _GUARD_HOOK_INSTALLED
    if _GUARD_HOOK_INSTALLED:
        return
    def hook(event, args):
        if _GUARD_DEPTH > 0 and event == 'open' and args and forbidden_path(args[0]):
            raise PermissionError('S1 calibration cannot access locked or consumed test data')
    sys.addaudithook(hook)
    _GUARD_HOOK_INSTALLED = True


def install_access_guard():
    _ensure_access_hook()
    global _GUARD_DEPTH
    _GUARD_DEPTH += 1


def release_access_guard():
    global _GUARD_DEPTH
    if _GUARD_DEPTH > 0:
        _GUARD_DEPTH -= 1


@contextmanager
def guarded_access():
    install_access_guard()
    try:
        yield
    finally:
        release_access_guard()

def safety_stop(metrics, baseline, generation=None):
    if any(not math.isfinite(metrics[k]) for k in ('wiki', 'tiny', 's1_macro', *BUCKETS)):
        return 'nonfinite_evaluation'
    if metrics['wiki'] > baseline['wiki'] + .05:
        return 'Wiki NLL > token-zero + 0.05'
    if metrics['tiny'] > baseline['tiny'] + .05:
        return 'Tiny NLL > token-zero + 0.05'
    if generation is not None:
        if generation['hard_failures'] / 96 >= .10:
            return 'hard/96 >= 10%'
        if len(generation['new_hard']) >= 3:
            return '>=3 new clean->hard prompts'
    return None

def dominates(a, b):
    keys = ('wiki', 'tiny', 's1_macro')
    return all(a[k] <= b[k] for k in keys) and any(a[k] < b[k] for k in keys)

def frontier(endpoints):
    valid = [r for r in endpoints if r['tokens'] == 409600 and r['valid']]
    nondominated = [r for r in valid if not any(dominates(q, r) for q in valid if q is not r)]
    winners = [r for r in valid if all(q is r or dominates(r, q) for q in valid)]
    return {'classification': 'S1_CALIBRATION_RETENTION_FAILURE' if not valid else
            'S1_CALIBRATION_CLEAR_WINNER' if len(winners) == 1 else 'S1_CALIBRATION_FRONTIER',
            'frontier': [r['cell'] for r in nondominated], 'unique_dominating_cell': winners[0]['cell'] if len(winners) == 1 else None,
            'endpoints': endpoints, 'endpoint_only': True, 'weighted_score': None}

def state_hash(value):
    """Stable full-state fingerprint including every per-parameter Adam step and RNG."""
    digest = hashlib.sha256()
    def visit(x):
        if torch.is_tensor(x):
            digest.update(str((x.dtype, tuple(x.shape))).encode())
            digest.update(x.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(x, dict):
            for k in sorted(x, key=str):
                digest.update(repr(k).encode()); visit(x[k])
        elif isinstance(x, (tuple, list)):
            digest.update(type(x).__name__.encode())
            for v in x: visit(v)
        elif hasattr(x, 'tobytes'):
            digest.update(str((x.dtype, x.shape)).encode()); digest.update(x.tobytes())
        else:
            digest.update(repr(x).encode())
    visit(value)
    return digest.hexdigest()
