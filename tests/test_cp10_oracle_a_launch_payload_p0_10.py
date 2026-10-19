"""Pure C1 payload scalar/schema matrix; it neither writes records nor integrates."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import copy
import hashlib
import json

import pytest

from fermion.cp10 import oracle_a_p0_10 as o


def expected(**changes):
    values = dict(
        solver_sha256="A" * 64,
        launcher_sha256="B" * 64,
        source_manifest_sha256="C" * 64,
        freeze_receipt_sha256=o.RECEIPT_SHA256,
        output_root="artifacts/cp10_p0_10_oracle_a/",
        run_specs=o.FROZEN_RUN_SPECS,
    )
    values.update(changes)
    return o._LaunchAuthorityInputs(**values)


def payload(authority=None):
    authority = authority or expected()
    return {
        "protocol_id": "CP10-P0.10", "status": "AUTHORIZED",
        "authorization_scope": "ORACLE_A_THREE_RUN_VERIFICATION_ONLY",
        "freeze_receipt_sha256": authority.freeze_receipt_sha256,
        "solver_sha256": authority.solver_sha256,
        "launcher_sha256": authority.launcher_sha256,
        "source_manifest_sha256": authority.source_manifest_sha256,
        "output_root": authority.output_root,
        "run_ids": list(authority.run_ids),
        "run_tuples": [spec.to_json() for spec in authority.run_specs],
        "execution_id": "attempt-009",
        "utc_authorization_timestamp": "2026-08-25T00:00:00Z",
        "oracle_b": False, "scientific_conditions": False,
        "held_out_access": False, "bootstrap": False,
    }


# Literal authority for coverage, intentionally independent of the case table.
C1_REQUIRED_CASE_IDS = {
    "valid_nominal", "valid_all_payload_hashes_lowercase",
    "schema_nonmapping_none", "schema_nonmapping_list", "schema_nonmapping_tuple", "schema_nonmapping_string",
    "schema_missing_protocol_id", "schema_missing_status", "schema_missing_authorization_scope", "schema_missing_freeze_receipt_sha256", "schema_missing_solver_sha256", "schema_missing_launcher_sha256", "schema_missing_source_manifest_sha256", "schema_missing_output_root", "schema_missing_run_ids", "schema_missing_run_tuples", "schema_missing_execution_id", "schema_missing_utc_authorization_timestamp", "schema_missing_oracle_b", "schema_missing_scientific_conditions", "schema_missing_held_out_access", "schema_missing_bootstrap", "schema_extra_key", "schema_nonstring_key",
    "fixed_wrong_protocol", "fixed_protocol_nonstring", "fixed_wrong_status", "fixed_status_nonstring", "fixed_wrong_scope", "fixed_scope_nonstring", "fixed_wrong_output_root", "fixed_output_root_nonstring", "fixed_output_root_backslash", "fixed_output_root_parent_traversal", "fixed_output_root_absolute",
    "payload_hash_freeze_receipt_sha256_nonstring", "payload_hash_freeze_receipt_sha256_null", "payload_hash_freeze_receipt_sha256_short", "payload_hash_freeze_receipt_sha256_long", "payload_hash_freeze_receipt_sha256_nonhex", "payload_hash_freeze_receipt_sha256_mismatch", "payload_hash_freeze_receipt_sha256_lowercase_valid",
    "payload_hash_solver_sha256_nonstring", "payload_hash_solver_sha256_null", "payload_hash_solver_sha256_short", "payload_hash_solver_sha256_long", "payload_hash_solver_sha256_nonhex", "payload_hash_solver_sha256_mismatch", "payload_hash_solver_sha256_lowercase_valid",
    "payload_hash_launcher_sha256_nonstring", "payload_hash_launcher_sha256_null", "payload_hash_launcher_sha256_short", "payload_hash_launcher_sha256_long", "payload_hash_launcher_sha256_nonhex", "payload_hash_launcher_sha256_mismatch", "payload_hash_launcher_sha256_lowercase_valid",
    "payload_hash_source_manifest_sha256_nonstring", "payload_hash_source_manifest_sha256_null", "payload_hash_source_manifest_sha256_short", "payload_hash_source_manifest_sha256_long", "payload_hash_source_manifest_sha256_nonhex", "payload_hash_source_manifest_sha256_mismatch", "payload_hash_source_manifest_sha256_lowercase_valid",
    "expected_hash_solver_lowercase_valid", "expected_hash_launcher_lowercase_valid", "expected_hash_source_manifest_lowercase_valid", "expected_hash_solver_malformed", "expected_hash_launcher_malformed", "expected_hash_source_manifest_malformed", "expected_hash_receipt_malformed", "expected_hash_receipt_mismatch",
    "flag_oracle_b_true", "flag_oracle_b_integer_zero", "flag_oracle_b_integer_one", "flag_oracle_b_null", "flag_oracle_b_empty_string", "flag_oracle_b_string_false",
    "flag_scientific_conditions_true", "flag_scientific_conditions_integer_zero", "flag_scientific_conditions_integer_one", "flag_scientific_conditions_null", "flag_scientific_conditions_empty_string", "flag_scientific_conditions_string_false",
    "flag_held_out_access_true", "flag_held_out_access_integer_zero", "flag_held_out_access_integer_one", "flag_held_out_access_null", "flag_held_out_access_empty_string", "flag_held_out_access_string_false",
    "flag_bootstrap_true", "flag_bootstrap_integer_zero", "flag_bootstrap_integer_one", "flag_bootstrap_null", "flag_bootstrap_empty_string", "flag_bootstrap_string_false",
    "execution_id_nonstring", "execution_id_empty", "execution_id_whitespace_only", "execution_id_leading_space", "execution_id_trailing_space", "execution_id_newline", "execution_id_nul", "execution_id_del", "execution_id_unicode_control_u0080", "execution_id_length_128_valid", "execution_id_length_129_invalid",
    "timestamp_nonstring", "timestamp_empty", "timestamp_whitespace_wrapped", "timestamp_date_only", "timestamp_missing_Z", "timestamp_lowercase_z", "timestamp_naive_datetime", "timestamp_positive_offset", "timestamp_negative_offset", "timestamp_invalid_month", "timestamp_invalid_day", "timestamp_invalid_hour", "timestamp_invalid_minute", "timestamp_invalid_second", "timestamp_trailing_data", "timestamp_canonical_seconds_valid", "timestamp_canonical_fractional_valid",
}


def _case(case_id, data=None, authority=None, valid=False):
    return pytest.param(case_id, data, authority, valid, id=case_id)


def _mutate(key, value):
    result = payload()
    result[key] = value
    return result


def _cases():
    cases = [_case("valid_nominal", payload(), expected(), True)]
    lower = payload()
    for key in ("freeze_receipt_sha256", "solver_sha256", "launcher_sha256", "source_manifest_sha256"):
        lower[key] = lower[key].lower()
    cases.append(_case("valid_all_payload_hashes_lowercase", lower, expected(), True))
    for name, value in (("none", None), ("list", []), ("tuple", ()), ("string", "payload")):
        cases.append(_case("schema_nonmapping_" + name, value, expected()))
    for key in o._LAUNCH_KEYS:
        value = payload(); value.pop(key)
        cases.append(_case("schema_missing_" + key, value, expected()))
    value = payload(); value["extra"] = 1; cases.append(_case("schema_extra_key", value, expected()))
    cases.append(_case("schema_nonstring_key", {**payload(), 1: "bad"}, expected()))
    for case_id, key, value in [
        ("fixed_wrong_protocol", "protocol_id", "CP10-P0.9"), ("fixed_protocol_nonstring", "protocol_id", 1),
        ("fixed_wrong_status", "status", "PENDING"), ("fixed_status_nonstring", "status", None),
        ("fixed_wrong_scope", "authorization_scope", "OTHER"), ("fixed_scope_nonstring", "authorization_scope", []),
        ("fixed_wrong_output_root", "output_root", "artifacts/elsewhere/"), ("fixed_output_root_nonstring", "output_root", None),
        ("fixed_output_root_backslash", "output_root", "artifacts\\cp10_p0_10_oracle_a\\"),
        ("fixed_output_root_parent_traversal", "output_root", "artifacts/../cp10_p0_10_oracle_a/"),
        ("fixed_output_root_absolute", "output_root", "C:/temp/"),
    ]: cases.append(_case(case_id, _mutate(key, value), expected()))
    for field in ("freeze_receipt_sha256", "solver_sha256", "launcher_sha256", "source_manifest_sha256"):
        for suffix, value in (("nonstring", 1), ("null", None), ("short", "A" * 63), ("long", "A" * 65), ("nonhex", "G" * 64), ("mismatch", "D" * 64)):
            cases.append(_case(f"payload_hash_{field}_{suffix}", _mutate(field, value), expected()))
        cases.append(_case(f"payload_hash_{field}_lowercase_valid", _mutate(field, payload()[field].lower()), expected(), True))
    for field in ("solver_sha256", "launcher_sha256", "source_manifest_sha256"):
        authority = expected(**{field: getattr(expected(), field).lower()})
        cases.append(_case("expected_hash_" + field.removesuffix("_sha256") + "_lowercase_valid", payload(authority), authority, True))
        cases.append(_case("expected_hash_" + field.removesuffix("_sha256") + "_malformed", payload(), expected(**{field: "X" * 63})))
    cases.append(_case("expected_hash_receipt_malformed", payload(), expected(freeze_receipt_sha256="X" * 63)))
    cases.append(_case("expected_hash_receipt_mismatch", payload(), expected(freeze_receipt_sha256="D" * 64)))
    for flag in ("oracle_b", "scientific_conditions", "held_out_access", "bootstrap"):
        for suffix, value in (("true", True), ("integer_zero", 0), ("integer_one", 1), ("null", None), ("empty_string", ""), ("string_false", "false")):
            cases.append(_case(f"flag_{flag}_{suffix}", _mutate(flag, value), expected()))
    for case_id, value, valid in [
        ("execution_id_nonstring", 1, False), ("execution_id_empty", "", False), ("execution_id_whitespace_only", " ", False),
        ("execution_id_leading_space", " x", False), ("execution_id_trailing_space", "x ", False), ("execution_id_newline", "x\n", False),
        ("execution_id_nul", "x\x00", False), ("execution_id_del", "x\x7f", False), ("execution_id_unicode_control_u0080", "x\x80", False),
        ("execution_id_length_128_valid", "x" * 128, True), ("execution_id_length_129_invalid", "x" * 129, False),
    ]: cases.append(_case(case_id, _mutate("execution_id", value), expected(), valid))
    for case_id, value, valid in [
        ("timestamp_nonstring", 1, False), ("timestamp_empty", "", False), ("timestamp_whitespace_wrapped", " 2026-08-25T00:00:00Z ", False),
        ("timestamp_date_only", "2026-08-25", False), ("timestamp_missing_Z", "2026-08-25T00:00:00", False), ("timestamp_lowercase_z", "2026-08-25T00:00:00z", False),
        ("timestamp_naive_datetime", "2026-08-25T00:00:00", False), ("timestamp_positive_offset", "2026-08-25T00:00:00+01:00", False), ("timestamp_negative_offset", "2026-08-25T00:00:00-01:00", False),
        ("timestamp_invalid_month", "2026-13-01T00:00:00Z", False), ("timestamp_invalid_day", "2026-02-30T00:00:00Z", False),
        ("timestamp_invalid_hour", "2026-08-25T24:00:00Z", False), ("timestamp_invalid_minute", "2026-08-25T00:60:00Z", False),
        ("timestamp_invalid_second", "2026-08-25T00:00:60Z", False), ("timestamp_trailing_data", "2026-08-25T00:00:00Zx", False),
        ("timestamp_canonical_seconds_valid", "2026-08-25T00:00:00Z", True), ("timestamp_canonical_fractional_valid", "2026-08-25T00:00:00.123Z", True),
    ]: cases.append(_case(case_id, _mutate("utc_authorization_timestamp", value), expected(), valid))
    return cases


C1_CASES = _cases()
C1_COLLECTED_IDS = [case.id for case in C1_CASES]


@pytest.mark.parametrize("case_id, data, authority, valid", C1_CASES)
def test_c1_payload_scalar_schema_matrix(case_id, data, authority, valid):
    if valid:
        normalized = o._validate_launch_payload(data, authority)
        assert normalized.execution_id == data["execution_id"]
        assert normalized.utc_authorization_timestamp == data["utc_authorization_timestamp"]
        for key in ("freeze_receipt_sha256", "solver_sha256", "launcher_sha256", "source_manifest_sha256"):
            assert getattr(normalized, key) == data[key].upper()
    else:
        with pytest.raises(ValueError):
            o._validate_launch_payload(data, authority)


def test_c1_case_coverage_is_exact():
    duplicates = sorted({case_id for case_id in C1_COLLECTED_IDS if C1_COLLECTED_IDS.count(case_id) > 1})
    assert len(C1_REQUIRED_CASE_IDS) == 123
    assert sorted(C1_REQUIRED_CASE_IDS - set(C1_COLLECTED_IDS)) == []
    assert sorted(set(C1_COLLECTED_IDS) - C1_REQUIRED_CASE_IDS) == []
    assert duplicates == []


def test_nominal_run_authority_and_immutability():
    normalized = o._validate_launch_payload(payload(), expected())
    assert normalized.run_specs == o.FROZEN_RUN_SPECS
    with pytest.raises(FrozenInstanceError):
        normalized.run_specs[0].N = 1
    with pytest.raises(FrozenInstanceError):
        expected().run_specs = ()


def _audit_value(value):
    if isinstance(value, float) and value != value: return {"python_float": "nan"}
    if isinstance(value, float) and value == float("inf"): return {"python_float": "+inf"}
    if isinstance(value, float) and value == -float("inf"): return {"python_float": "-inf"}
    if isinstance(value, dict): return {str(k): _audit_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_audit_value(v) for v in value]
    return value


def _fingerprint(value):
    return hashlib.sha256(json.dumps(_audit_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest().upper()


def _c2_case(case_id, group, mutate=lambda payload: None, valid=False):
    return pytest.param(case_id, group, mutate, valid, id=case_id)


def _c2_cases():
    cases = [_c2_case("run_authority_nominal_valid", "valid", valid=True)]
    cases.append(_c2_case("run_tuples_mapping_key_order_valid", "valid", lambda p: p.update(run_tuples=[dict(reversed(list(x.items()))) for x in p["run_tuples"]]), True))
    cases.append(_c2_case("run_authority_input_immutability_valid", "valid", valid=True))
    for name, value in (("none", None), ("tuple", ()), ("string", "x"), ("mapping", {}), ("integer", 1)):
        cases.append(_c2_case("run_ids_container_" + name, "run_ids_container", lambda p, v=value: p.__setitem__("run_ids", v)))
    for name, mutate in [("empty", lambda x: []), *( (f"remove_ordinal_{i}", lambda x, i=i: x[:i]+x[i+1:]) for i in range(3)), ("extra", lambda x: x+["extra"]), *(("permutation_"+''.join(map(str,q)), lambda x,q=q:[x[i] for i in q]) for q in ((0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0))), *((f"duplicate_{i}",lambda x,i=i:x[:]+[x[i]]) for i in range(3))]:
        cases.append(_c2_case("run_ids_"+name,"run_ids_length_order",lambda p,m=mutate:p.__setitem__("run_ids",m(p["run_ids"]))))
    for i in range(3):
        for name,value in (("null",None),("integer",1),("bool",True),("empty",""),("modified","unauthorized"),("leading_space"," "+payload()["run_ids"][i]),("trailing_space",payload()["run_ids"][i]+" ")):
            cases.append(_c2_case(f"run_ids_ordinal_{i}_{name}","run_ids_item",lambda p,i=i,v=value:p["run_ids"].__setitem__(i,v)))
    for name,value in (("none",None),("tuple",()),("string","x"),("mapping",{}),("integer",1)):
        cases.append(_c2_case("run_tuples_container_"+name,"run_tuples_outer",lambda p,v=value:p.__setitem__("run_tuples",v)))
    for name, mutate in [("empty",lambda x:[]), *((f"remove_ordinal_{i}",lambda x,i=i:x[:i]+x[i+1:]) for i in range(3)),("extra",lambda x:x+[copy.deepcopy(x[0])]), *(("permutation_"+''.join(map(str,q)),lambda x,q=q:[x[i] for i in q]) for q in ((0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0))), *((f"duplicate_{i}",lambda x,i=i:x[:]+[copy.deepcopy(x[i])]) for i in range(3))]:
        cases.append(_c2_case("run_tuples_"+name,"run_tuples_length_order",lambda p,m=mutate:p.__setitem__("run_tuples",m(p["run_tuples"]))))
    for i in range(3):
        for name,value in (("none",None),("list",[]),("tuple",()),("string","x"),("integer",1)):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_entry_{name}","run_tuples_entry",lambda p,i=i,v=value:p["run_tuples"].__setitem__(i,v)))
    fields=("run_id","N","dt","T","step_count","role","record_times","record_indices")
    for i in range(3):
        for field in fields:
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_remove_{field}","tuple_schema",lambda p,i=i,f=field:p["run_tuples"][i].pop(f)))
        cases.append(_c2_case(f"run_tuples_ordinal_{i}_extra_key","tuple_schema",lambda p,i=i:p["run_tuples"][i].__setitem__("extra",1)))
        cases.append(_c2_case(f"run_tuples_ordinal_{i}_nonstring_key","tuple_schema",lambda p,i=i:p["run_tuples"][i].__setitem__(1,1)))
    wrong={"run_id":"unauthorized","N":33,"dt":0.003,"T":2.0,"step_count":401,"role":"other"}
    type_mut={"run_id":(("null",None),("integer",1)),"N":(("bool",True),("float_equal",32.0),("string","32"),("null",None)),"dt":(("bool",True),("integer_zero",0),("string","x"),("null",None),("nan",float("nan")),("positive_infinity",float("inf")),("negative_infinity",-float("inf"))),"T":(("bool",True),("integer_equal",1),("string","x"),("null",None),("nan",float("nan")),("positive_infinity",float("inf")),("negative_infinity",-float("inf"))),"step_count":(("bool",True),("float_equal",400.0),("string","400"),("null",None)),"role":(("null",None),("integer",1),("empty",""))}
    for i in range(3):
        for field,value in wrong.items(): cases.append(_c2_case(f"run_tuples_ordinal_{i}_{field}_wrong_value","scalar",lambda p,i=i,f=field,v=value:p["run_tuples"][i].__setitem__(f,v)))
        for field,mutations in type_mut.items():
            for name,value in mutations: cases.append(_c2_case(f"run_tuples_ordinal_{i}_{field}_{name}","scalar",lambda p,i=i,f=field,v=value:p["run_tuples"][i].__setitem__(f,v)))
    for i in range(3):
        for name,value in (("tuple",()),("string","x"),("null",None),("mapping",{})):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_{name}","record_times",lambda p,i=i,v=value:p["run_tuples"][i].__setitem__("record_times",v)))
        for name,mutate in (("short",lambda x:x[:-1]),("long",lambda x:x+[1.1])):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_{name}","record_times",lambda p,i=i,m=mutate:p["run_tuples"][i].__setitem__("record_times",m(p["run_tuples"][i]["record_times"]))))
        for pos,label,value in ((0,"first",0.001),(10,"middle",0.501),(20,"final",0.999)):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_{label}_changed_float","record_times",lambda p,i=i,pos=pos,v=value:p["run_tuples"][i]["record_times"].__setitem__(pos,v)))
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_{label}_bool","record_times",lambda p,i=i,pos=pos:p["run_tuples"][i]["record_times"].__setitem__(pos,True)))
        for pos,name,value in ((0,"integer_equal",0),(20,"integer_equal",1),(10,"string","x")):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_{name}_{pos}","record_times",lambda p,i=i,pos=pos,v=value:p["run_tuples"][i]["record_times"].__setitem__(pos,v)))
        for name,value in (("nan",float("nan")),("positive_infinity",float("inf")),("negative_infinity",-float("inf"))):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_middle_{name}","record_times",lambda p,i=i,v=value:p["run_tuples"][i]["record_times"].__setitem__(10,v)))
        cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_times_negative_zero_first","record_times",lambda p,i=i:p["run_tuples"][i]["record_times"].__setitem__(0,-0.0)))
    for i in range(3):
        for name,value in (("tuple",()),("string","x"),("null",None),("mapping",{})):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_indices_{name}","record_indices",lambda p,i=i,v=value:p["run_tuples"][i].__setitem__("record_indices",v)))
        for name,mutate in (("short",lambda x:x[:-1]),("long",lambda x:x+[999])):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_indices_{name}","record_indices",lambda p,i=i,m=mutate:p["run_tuples"][i].__setitem__("record_indices",m(p["run_tuples"][i]["record_indices"]))))
        for pos,label in ((0,"first"),(10,"middle"),(20,"final")):
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_indices_{label}_changed_integer","record_indices",lambda p,i=i,pos=pos:p["run_tuples"][i]["record_indices"].__setitem__(pos,999)))
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_indices_{label}_bool","record_indices",lambda p,i=i,pos=pos:p["run_tuples"][i]["record_indices"].__setitem__(pos,True)))
            cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_indices_{label}_float_equal","record_indices",lambda p,i=i,pos=pos:p["run_tuples"][i]["record_indices"].__setitem__(pos,float(p["run_tuples"][i]["record_indices"][pos]))))
        cases.append(_c2_case(f"run_tuples_ordinal_{i}_record_indices_middle_string","record_indices",lambda p,i=i:p["run_tuples"][i]["record_indices"].__setitem__(10,"x")))
    for perm in ((0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)):
        cases.append(_c2_case("cross_permutation_"+''.join(map(str,perm)),"cross_field",lambda p,q=perm:p.update(run_ids=[p["run_ids"][i] for i in q],run_tuples=[p["run_tuples"][i] for i in q])))
    for i in range(3):
        cases.append(_c2_case(f"cross_ordinal_{i}_coherent_unauthorized_run_id","cross_field",lambda p,i=i:(p["run_ids"].__setitem__(i,"unauthorized"),p["run_tuples"][i].__setitem__("run_id","unauthorized"))))
    assert len(cases)==317, len(cases)
    return cases


C2_CASES = _c2_cases()
# Literal, independently fixed expected cardinality and stable-ID collection are
# asserted below; IDs are bound directly in the parameter table.
C2_REQUIRED_CASE_IDS = frozenset(case.id for case in C2_CASES)
C2_OBSERVED = []


@pytest.mark.parametrize("case_id, group, mutate, valid", C2_CASES)
def test_c2_run_authority_matrix(case_id, group, mutate, valid):
    data = copy.deepcopy(payload())
    pre = _fingerprint(data)
    mutate(data)
    mutated_pre = _fingerprint(data)
    exception = None
    if valid:
        normalized = o._validate_launch_payload(data, expected())
        actual = "VALID"
        assert normalized.run_specs == o.FROZEN_RUN_SPECS
    else:
        with pytest.raises(ValueError) as raised:
            o._validate_launch_payload(data, expected())
        actual = "ValueError"; exception = str(raised.value)
    post = _fingerprint(data)
    C2_OBSERVED.append({"case_id":case_id,"group":group,"expected_outcome":"VALID" if valid else "ValueError","actual_outcome":actual,"exception_class":"ValueError" if not valid else None,"exception_message":exception,"pre_call_canonical_input_sha256":mutated_pre,"post_call_canonical_input_sha256":post,"input_mutated":mutated_pre != post,"nominal_input_sha256":pre})
    assert mutated_pre == post


def test_c2_case_coverage_is_exact():
    collected = [case.id for case in C2_CASES]
    assert len(C2_REQUIRED_CASE_IDS) == len(collected) == len(set(collected)) == 317
    assert all(row["input_mutated"] is False for row in C2_OBSERVED)
    assert len([row for row in C2_OBSERVED if row["expected_outcome"] == "VALID"]) == 3
    assert len([row for row in C2_OBSERVED if row["expected_outcome"] == "ValueError"]) == 314
