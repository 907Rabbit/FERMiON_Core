"""Contracts for the single authorized S1 continuation; no promotion access."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
import torch
from . import s1_calibration as cal

BLOCK_COUNTS = dict(cal.COUNTS['s1_25'])
TOTAL_COUNTS = {k: v * 5 for k, v in BLOCK_COUNTS.items()}
GRID = tuple(i * 409600 for i in range(6))
AXES = ('wiki', 'tiny', 's1_macro')

_CON_HOOK_INSTALLED = False


def install_access_guard():
    cal.install_access_guard()
    global _CON_HOOK_INSTALLED
    if _CON_HOOK_INSTALLED:
        return
    def guard(event, args):
        if not cal.guard_is_active(): return
        if event != 'open' or not args or isinstance(args[0], int): return
        path = os.path.realpath(os.fsdecode(args[0]))
        if cal.forbidden_path(path):
            raise PermissionError('S1 continuation cannot access locked or consumed data')
    sys.addaudithook(guard)
    _CON_HOOK_INSTALLED = True


def release_access_guard():
    cal.release_access_guard()

def schedule():
    blocks = []
    for block in range(5):
        entries = [(hashlib.sha256(f'S1_LONG_V1:{block}:{source}:{i}'.encode()).hexdigest(), source)
                   for source, n in BLOCK_COUNTS.items() for i in range(n)]
        blocks.append([source for _, source in sorted(entries)])
    return [s for block in blocks for s in block]

def audit_counts(sources, position, counts):
    expected = {s: 0 for s in TOTAL_COUNTS}
    expected.update(Counter(sources[:position]))
    if counts != expected or not 0 <= position <= 4000:
        raise ValueError('S1_CONTINUATION_SOURCE_SCHEDULE_FAILURE')
    if position % 800 == 0 and counts != {s: n * (position // 800) for s, n in BLOCK_COUNTS.items()}:
        raise ValueError('S1_CONTINUATION_SOURCE_SCHEDULE_FAILURE: block')

def validate_winner(frontier, result):
    if (frontier['classification'] != 'S1_CALIBRATION_CLEAR_WINNER'
        or frontier['unique_dominating_cell'] != 's1_25'
        or result['cell'] != 's1_25' or result['tokens'] != 409600
        or not result['valid'] or result['generation']['status'] != 'PASS'):
        raise ValueError('S1_CONTINUATION_RESUME_FAILURE: unauthorized base')

def optimizer_fingerprint(opt):
    sd = opt.state_dict() if hasattr(opt, 'state_dict') else opt
    if not sd['state']:
        raise ValueError('S1_CONTINUATION_RESUME_FAILURE: fresh optimizer')
    for state in sd['state'].values():
        if not all(k in state for k in ('step', 'exp_avg', 'exp_avg_sq')):
            raise ValueError('S1_CONTINUATION_RESUME_FAILURE: missing Adam state')
        if any(not bool(torch.isfinite(state[k]).all()) for k in ('step', 'exp_avg', 'exp_avg_sq')):
            raise ValueError('S1_CONTINUATION_CHECKPOINT_FAILURE: nonfinite Adam state')
    return {'full': cal.state_hash(sd),
            'moments': cal.state_hash({k: (s['exp_avg'], s['exp_avg_sq']) for k, s in sd['state'].items()}),
            'steps': cal.state_hash({k: s['step'] for k, s in sd['state'].items()}),
            'parameter_states': len(sd['state'])}

def relation(point, champion):
    if cal.dominates(point, champion): return 'DOMINATES_PRODUCTION_CHAMPION'
    if cal.dominates(champion, point): return 'DOMINATED_BY_PRODUCTION_CHAMPION'
    return 'NONDOMINATED_WITH_PRODUCTION_CHAMPION'

def eligible(point):
    return (point['additional_tokens'] > 0 and point['generation']['status'] == 'PASS'
            and point['stop_reason'] is None and point['checkpoint_verified'])

def frontier(points):
    valid = [p for p in points if eligible(p)]
    return [p for p in valid if not any(cal.dominates(q, p) for q in valid)]

def update_historical(history, points):
    result = copy.deepcopy(history)
    newest = points[-1]
    if newest in frontier(points) and newest['checkpoint'] not in {p['checkpoint'] for p in result}:
        result.append(copy.deepcopy(newest))
    return result

def classification(points, stop):
    if stop and stop.startswith('S1_CONTINUATION_'): return stop.split(':')[0]
    # The explicit no-useful-state rule takes precedence when no trained point passes.
    if not any(eligible(p) for p in points): return 'S1_LONG_CONTINUATION_NO_USEFUL_STATE'
    if stop: return 'S1_LONG_CONTINUATION_RETENTION_LIMIT'
    if points[-1]['additional_tokens'] == 2048000: return 'S1_LONG_CONTINUATION_COMPLETE'
    return 'S1_CONTINUATION_INVALID'

def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.pending')
    with temporary.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)
