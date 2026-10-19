"""Scoping/lifetime contract for the process-global locked-data audit guard.

The audit hook is installed once per process and never removed; enforcement is
reference-counted so it is active only inside an authorized protection scope and
cannot leak into unrelated later code. Forbidden-path rules themselves are
unchanged and verified elsewhere.
"""
import pytest

from fermion_llm.training import s1_calibration as cal
from fermion_llm.training import s1_continuation as con


def _attempt_open(tmp_path):
    target = tmp_path / 'data' / 'promotion_v4_1_external'
    target.mkdir(parents=True, exist_ok=True)
    f = target / 'x.bin'
    try:
        with open(f, 'wb') as handle:
            handle.write(b'x')
        return 'ALLOWED'
    except PermissionError:
        return 'BLOCKED'


def test_inactive_guard_allows_forbidden_named_path(tmp_path):
    assert not cal.guard_is_active()
    assert _attempt_open(tmp_path) == 'ALLOWED'


def test_active_guard_blocks_and_scope_restores(tmp_path):
    with cal.guarded_access():
        assert cal.guard_is_active()
        assert _attempt_open(tmp_path) == 'BLOCKED'
    assert not cal.guard_is_active()
    assert _attempt_open(tmp_path) == 'ALLOWED'


def test_exception_exit_restores():
    with pytest.raises(RuntimeError):
        with cal.guarded_access():
            assert cal.guard_is_active()
            raise RuntimeError('boom')
    assert not cal.guard_is_active()


def test_nested_scopes_active_until_outermost_exit():
    with cal.guarded_access():
        with cal.guarded_access():
            assert cal.guard_is_active()
        assert cal.guard_is_active()
    assert not cal.guard_is_active()


def test_install_is_idempotent_and_refcounted():
    base = cal._GUARD_DEPTH
    cal.install_access_guard()
    cal.install_access_guard()
    assert cal._GUARD_HOOK_INSTALLED is True
    assert cal._GUARD_DEPTH == base + 2 and cal.guard_is_active()
    cal.release_access_guard()
    cal.release_access_guard()
    assert cal._GUARD_DEPTH == base


def test_continuation_guard_shares_refcount(tmp_path):
    con.install_access_guard()
    try:
        assert cal.guard_is_active()
        assert _attempt_open(tmp_path) == 'BLOCKED'
    finally:
        con.release_access_guard()
    assert not cal.guard_is_active()
