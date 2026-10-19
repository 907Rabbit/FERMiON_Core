import json

from fermion.adapters.ciphey import decode_ciphertext
from fermion.control_plane import default_control_plane


def test_ciphey_decodes_user_supplied_base64_without_launching_the_binary(tmp_path):
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("Decode this", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "ciphey", "operation": "decode",
                     "arguments": {"ciphertext": "SGVsbG8="}}],
    }))
    report = plane.execute(plan, approved=True)
    assert report.validation.valid
    details = report.records[0].result.details
    assert details["vendored_ciphey_executed"] is False
    assert any(item["plaintext"] == "Hello" for item in details["candidates"])


def test_decode_ciphertext_rejects_empty_and_oversized_input():
    try:
        decode_ciphertext("  ")
        raise AssertionError("empty ciphertext should fail")
    except ValueError:
        pass
    try:
        decode_ciphertext("A" * 9000)
        raise AssertionError("oversized ciphertext should fail")
    except ValueError:
        pass


def test_gods_eye_view_is_not_an_inspect_only_attack_surface(tmp_path):
    plane = default_control_plane(tmp_path)
    assert plane._applications["gods_eye_view"].specification("start") is not None
    assert plane._applications["bettercap"].specification("start") is None


def test_live_attack_applications_are_registered_but_do_not_launch(tmp_path):
    plane = default_control_plane(tmp_path)
    for name in ("bettercap", "hackingtool", "ghosttrack", "spiderfoot", "codex"):
        assert name in plane.manifest()
        assert plane._applications[name].specification("status") is not None
        assert plane._applications[name].specification("scan") is None
        assert plane._applications[name].specification("attack") is None
        assert plane._applications[name].specification("launch") is None
    plan = plane.parse_plan("Status only", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "bettercap", "operation": "status", "arguments": {}}],
    }))
    report = plane.execute(plan, approved=True)
    assert report.validation.valid
    assert report.records[0].result.details["live_execution"] is False


def test_spiderfoot_catalog_is_filenames_not_a_scan(tmp_path):
    plane = default_control_plane(tmp_path)
    plan = plane.parse_plan("List spiderfoot modules", json.dumps({
        "requires_approval": False,
        "actions": [{"application": "spiderfoot", "operation": "list_catalog", "arguments": {}}],
    }))
    report = plane.execute(plan, approved=True)
    assert report.validation.valid
    details = report.records[0].result.details
    assert details["launched"] is False
    assert details["live_execution"] is False
