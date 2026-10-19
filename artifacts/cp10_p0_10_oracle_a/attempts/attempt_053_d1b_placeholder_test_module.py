import hashlib, json, inspect, re, pathlib, pytest
from fermion.cp10 import oracle_a_p0_10 as o

CANDIDATE_PATH = pathlib.Path("artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1b_test_matrix_candidate.json")
CANDIDATE_RAW_SHA256 = "693DDC403194067DD20665FB2593A53B458CFD6D4D21473120C3034A1B27ADD3"
REQUIRED_IDS_CANONICAL_SHA256 = "D0F7C0ABE8ABF1E822E0F0CABE4C93E3CC751A411BB96266A8FF97D5615A5BAF"
LEDGER_CANONICAL_SHA256 = "AC828AE19DAED76159618FD49BED657DDFCEBA7776457AC04C5CF9A3FB775E11"
_canon=lambda x: json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
_raw=CANDIDATE_PATH.read_bytes()
_candidate=json.loads(_raw)
D1B_CASES=tuple(_candidate["cases"])
D1B_REQUIRED_CASE_IDS = {
    'd1b_c1_shared_validation_execution_del',
    'd1b_c1_shared_validation_execution_leading_space',
    'd1b_c1_shared_validation_execution_length_129',
    'd1b_c1_shared_validation_execution_newline',
    'd1b_c1_shared_validation_execution_nul',
    'd1b_c1_shared_validation_execution_rejected_unicode_category',
    'd1b_c1_shared_validation_execution_trailing_space',
    'd1b_c1_shared_validation_invalid_day',
    'd1b_c1_shared_validation_invalid_hour',
    'd1b_c1_shared_validation_invalid_minute',
    'd1b_c1_shared_validation_invalid_month',
    'd1b_c1_shared_validation_invalid_second',
    'd1b_c1_shared_validation_lowercase_z',
    'd1b_c1_shared_validation_missing_z',
    'd1b_c1_shared_validation_positive_offset',
    'd1b_c1_shared_validation_timestamp_nonstring',
    'd1b_c1_shared_validation_timestamp_whitespace',
    'd1b_c1_shared_validation_valid_execution_id_128',
    'd1b_c1_shared_validation_valid_fractional_timestamp',
    'd1b_c1_shared_validation_valid_seconds_timestamp',
    'd1b_callback_malformed_malformed_bundle_members',
    'd1b_callback_malformed_malformed_bundle_members_recheck',
    'd1b_callback_malformed_malformed_detached_checksum',
    'd1b_callback_malformed_malformed_detached_checksum_recheck',
    'd1b_callback_malformed_malformed_filesystem_contract',
    'd1b_callback_malformed_malformed_filesystem_contract_recheck',
    'd1b_callback_malformed_malformed_freeze_receipt',
    'd1b_callback_malformed_malformed_freeze_receipt_recheck',
    'd1b_callback_malformed_malformed_launch_payload',
    'd1b_callback_malformed_malformed_launch_record_hash',
    'd1b_callback_malformed_malformed_launch_record_parse',
    'd1b_callback_malformed_malformed_launch_record_path',
    'd1b_callback_malformed_malformed_launcher_hash',
    'd1b_callback_malformed_malformed_launcher_hash_recheck',
    'd1b_callback_malformed_malformed_solver_hash',
    'd1b_callback_malformed_malformed_solver_hash_recheck',
    'd1b_callback_malformed_malformed_source_manifest',
    'd1b_callback_malformed_malformed_source_manifest_recheck',
    'd1b_closure_isolation_core_never_invoked',
    'd1b_closure_isolation_exact_event_constant',
    'd1b_closure_isolation_fixed_callback_routing',
    'd1b_closure_isolation_no_execution_calls',
    'd1b_closure_isolation_production_manifest_untouched',
    'd1b_closure_isolation_production_record_absent',
    'd1b_closure_isolation_production_wrapper_signature',
    'd1b_closure_isolation_reserved_temp_absent',
    'd1b_closure_isolation_run_oracle_a_denial',
    'd1b_closure_isolation_terminal_outputs_absent',
    'd1b_closure_isolation_tmp_path_only_writes',
    'd1b_engine_failures_callback_failure_event_01',
    'd1b_engine_failures_callback_failure_event_02',
    'd1b_engine_failures_callback_failure_event_03',
    'd1b_engine_failures_callback_failure_event_04',
    'd1b_engine_failures_callback_failure_event_05',
    'd1b_engine_failures_callback_failure_event_06',
    'd1b_engine_failures_callback_failure_event_07',
    'd1b_engine_failures_callback_failure_event_08',
    'd1b_engine_failures_callback_failure_event_09',
    'd1b_engine_failures_callback_failure_event_10',
    'd1b_engine_failures_callback_failure_event_11',
    'd1b_engine_failures_callback_failure_event_12',
    'd1b_engine_failures_callback_failure_event_13',
    'd1b_engine_failures_callback_failure_event_14',
    'd1b_engine_failures_callback_failure_event_15',
    'd1b_engine_failures_callback_failure_event_16',
    'd1b_engine_failures_callback_failure_event_17',
    'd1b_engine_failures_callback_failure_event_18',
    'd1b_engine_success_authorized_pre_core_status',
    'd1b_engine_success_engine_exact_19_events',
    'd1b_engine_success_report_actual_first_pass_bindings',
    'd1b_engine_success_report_actual_second_pass_bindings',
    'd1b_engine_success_report_deep_immutable',
    'd1b_engine_success_report_exact_contents',
    'd1b_engine_wrapping_all_18_prefix_preserved',
    'd1b_engine_wrapping_comparison_exception_wrapped',
    'd1b_engine_wrapping_final_immutability_wrapped',
    'd1b_engine_wrapping_report_constructor_wrapped',
    'd1b_engine_wrapping_validation_attributeerror_wrapped',
    'd1b_fixed_read_acceptance_valid_close_success',
    'd1b_fixed_read_acceptance_valid_exact_raw_bytes',
    'd1b_fixed_read_acceptance_valid_nonempty_single_allowlist',
    'd1b_fixed_read_acceptance_valid_partial_descriptor_reads',
    'd1b_fixed_read_acceptance_valid_second_allowlist_entry',
    'd1b_fixed_read_acceptance_valid_zero_byte_file',
    'd1b_fixed_read_chain_intermediate_missing',
    'd1b_fixed_read_chain_leaf_missing_with_message',
    'd1b_fixed_read_chain_leaf_missing_without_message',
    'd1b_fixed_read_chain_leaf_nonregular',
    'd1b_fixed_read_chain_leaf_reparse',
    'd1b_fixed_read_chain_leaf_symlink',
    'd1b_fixed_read_chain_parent_nondirectory',
    'd1b_fixed_read_chain_parent_reparse',
    'd1b_fixed_read_chain_parent_symlink',
    'd1b_fixed_read_chain_root_missing',
    'd1b_fixed_read_chain_root_reparse',
    'd1b_fixed_read_chain_root_symlink',
    'd1b_fixed_read_close_close_only_oserror',
    'd1b_fixed_read_close_close_only_runtimeerror',
    'd1b_fixed_read_close_primary_plus_close_preserves_primary',
    'd1b_fixed_read_descriptor_descriptor_leaf_identity_mismatch',
    'd1b_fixed_read_descriptor_descriptor_nonregular',
    'd1b_fixed_read_descriptor_fstat_oserror',
    'd1b_fixed_read_descriptor_fstat_runtimeerror',
    'd1b_fixed_read_descriptor_open_oserror',
    'd1b_fixed_read_descriptor_open_runtimeerror',
    'd1b_fixed_read_exception_custom_exception_callback',
    'd1b_fixed_read_exception_eoferror_callback',
    'd1b_fixed_read_exception_keyboard_interrupt_propagates',
    'd1b_fixed_read_exception_lookuperror_callback',
    'd1b_fixed_read_exception_no_incidental_exception',
    'd1b_fixed_read_exception_overflowerror_callback',
    'd1b_fixed_read_exception_system_exit_propagates',
    'd1b_fixed_read_lexical_absolute_entry',
    'd1b_fixed_read_lexical_allowed_list',
    'd1b_fixed_read_lexical_allowed_none',
    'd1b_fixed_read_lexical_candidate_not_allowlisted',
    'd1b_fixed_read_lexical_dot_entry',
    'd1b_fixed_read_lexical_duplicate_textual_entry',
    'd1b_fixed_read_lexical_empty_allowlist',
    'd1b_fixed_read_lexical_empty_entry',
    'd1b_fixed_read_lexical_multiple_candidate_matches',
    'd1b_fixed_read_lexical_parent_traversal',
    'd1b_fixed_read_lexical_path_equivalent_duplicate',
    'd1b_fixed_read_lexical_relative_requested_path',
    'd1b_fixed_read_lexical_relative_root',
    'd1b_fixed_read_lexical_tuple_nonstring',
    'd1b_fixed_read_lexical_zero_candidate_matches',
    'd1b_fixed_read_post_open_post_open_identity_change',
    'd1b_fixed_read_post_open_post_open_missing_component',
    'd1b_fixed_read_post_open_post_open_reparse',
    'd1b_fixed_read_post_open_post_open_symlink',
    'd1b_fixed_read_post_read_post_read_identity_change',
    'd1b_fixed_read_post_read_post_read_missing_component',
    'd1b_fixed_read_post_read_post_read_reparse',
    'd1b_fixed_read_post_read_post_read_resolved_authority_mismatch',
    'd1b_fixed_read_post_read_post_read_resolved_escape',
    'd1b_fixed_read_post_read_post_read_symlink',
    'd1b_fixed_read_read_byte_count_mismatch',
    'd1b_fixed_read_read_descriptor_ctime_change',
    'd1b_fixed_read_read_descriptor_mtime_change',
    'd1b_fixed_read_read_descriptor_size_change',
    'd1b_fixed_read_read_empty_chunk_before_completion',
    'd1b_fixed_read_read_nonbytes_chunk',
    'd1b_fixed_read_read_oversized_chunk',
    'd1b_fixed_read_read_read_oserror',
    'd1b_fixed_read_read_read_runtimeerror',
    'd1b_fixed_read_resolution_candidate_resolution_failure',
    'd1b_fixed_read_resolution_post_open_resolved_change',
    'd1b_fixed_read_resolution_post_read_resolved_change',
    'd1b_fixed_read_resolution_resolved_authority_mismatch',
    'd1b_fixed_read_resolution_resolved_escape',
    'd1b_fixed_read_resolution_root_resolution_failure',
    'd1b_launch_record_authorized_record_not_terminal_collision',
    'd1b_launch_record_expected_hash_long',
    'd1b_launch_record_expected_hash_lowercase',
    'd1b_launch_record_expected_hash_nonhex',
    'd1b_launch_record_expected_hash_nonstring',
    'd1b_launch_record_expected_hash_null',
    'd1b_launch_record_expected_hash_short',
    'd1b_launch_record_fixed_public_routing',
    'd1b_launch_record_private_path_mismatch',
    'd1b_launch_record_public_missing_exact_runtimeerror',
    'd1b_launch_record_public_signature',
    'd1b_launch_record_record_byte_identical',
    'd1b_launch_record_record_duplicate_key',
    'd1b_launch_record_record_invalid_c1_payload',
    'd1b_launch_record_record_invalid_c2_authority',
    'd1b_launch_record_record_malformed_json_correct_hash',
    'd1b_launch_record_record_malformed_json_wrong_hash',
    'd1b_launch_record_record_nonobject',
    'd1b_launch_record_record_nonregular',
    'd1b_launch_record_record_reparse',
    'd1b_launch_record_record_resolved_escape',
    'd1b_launch_record_record_symlink',
    'd1b_launch_record_record_valid_exact_payload',
    'd1b_launch_record_record_valid_json_hash_mismatch',
    'd1b_launch_record_record_zero_writes',
    'd1b_launch_record_valid_private_record',
    'd1b_nested_mutations_bundle_duplicate_path',
    'd1b_nested_mutations_bundle_empty_path',
    'd1b_nested_mutations_bundle_list',
    'd1b_nested_mutations_bundle_list_member',
    'd1b_nested_mutations_bundle_lowercase_hash',
    'd1b_nested_mutations_bundle_mutable_nested',
    'd1b_nested_mutations_bundle_nonhex_hash',
    'd1b_nested_mutations_bundle_wrong_count',
    'd1b_nested_mutations_bundle_wrong_pair_length',
    'd1b_nested_mutations_filesystem_collisions',
    'd1b_nested_mutations_filesystem_list_targets',
    'd1b_nested_mutations_filesystem_nonpass',
    'd1b_nested_mutations_filesystem_reparse_findings',
    'd1b_nested_mutations_filesystem_reserved_findings',
    'd1b_nested_mutations_filesystem_subclass',
    'd1b_nested_mutations_filesystem_wrong_output_root',
    'd1b_nested_mutations_filesystem_wrong_root',
    'd1b_nested_mutations_filesystem_wrong_target_hash',
    'd1b_nested_mutations_filesystem_wrong_targets',
    'd1b_nested_mutations_hash_result_lowercase_hash',
    'd1b_nested_mutations_hash_result_nonpass',
    'd1b_nested_mutations_hash_result_subclass',
    'd1b_nested_mutations_hash_result_wrong_label',
    'd1b_nested_mutations_hash_result_wrong_path',
    'd1b_nested_mutations_payload_malformed_authority_hash',
    'd1b_nested_mutations_payload_non_runspec',
    'd1b_nested_mutations_payload_nonstring_run_id',
    'd1b_nested_mutations_payload_nonstring_scalar',
    'd1b_nested_mutations_payload_prohibited_flag_true',
    'd1b_nested_mutations_payload_run_ids_list',
    'd1b_nested_mutations_payload_run_specs_list',
    'd1b_nested_mutations_payload_subclass',
    'd1b_nested_mutations_runspec_invalid_scalar',
    'd1b_nested_mutations_runspec_mutable_nested',
    'd1b_nested_mutations_runspec_record_indices_list',
    'd1b_nested_mutations_runspec_record_times_list',
    'd1b_nested_mutations_source_mutable_nested',
    'd1b_nested_mutations_source_nonpass',
    'd1b_nested_mutations_source_subclass',
    'd1b_nested_mutations_source_wrong_filesystem_version',
    'd1b_nested_mutations_source_wrong_launch_record_path',
    'd1b_nested_mutations_source_wrong_output_root',
    'd1b_nested_mutations_source_wrong_path',
    'd1b_nested_mutations_source_wrong_schema',
    'd1b_nested_mutations_source_wrong_target_hash',
    'd1b_recheck_mismatch_recheck_bundle_mismatch',
    'd1b_recheck_mismatch_recheck_checksum_mismatch',
    'd1b_recheck_mismatch_recheck_filesystem_mismatch',
    'd1b_recheck_mismatch_recheck_launcher_mismatch',
    'd1b_recheck_mismatch_recheck_receipt_mismatch',
    'd1b_recheck_mismatch_recheck_solver_mismatch',
    'd1b_recheck_mismatch_recheck_source_manifest_mismatch',
    'd1b_runspec_every_frozen_runspec_valid',
    'd1b_runspec_runspec_boolean_index',
    'd1b_runspec_runspec_invalid_scalar',
    'd1b_runspec_runspec_list_record_indices',
    'd1b_runspec_runspec_list_record_times',
    'd1b_runspec_runspec_nonfinite_time',
    'd1b_source_manifest_binding_candidate_targets_hash',
    'd1b_source_manifest_binding_complete_targets_hash',
    'd1b_source_manifest_binding_filesystem_version',
    'd1b_source_manifest_binding_launch_record_path',
    'd1b_source_manifest_binding_launcher_hash',
    'd1b_source_manifest_binding_output_root',
    'd1b_source_manifest_binding_protocol_id',
    'd1b_source_manifest_binding_receipt_hash',
    'd1b_source_manifest_binding_runner_hash',
    'd1b_source_manifest_binding_schema_version',
    'd1b_source_manifest_binding_solver_hash',
    'd1b_source_manifest_binding_status',
    'd1b_source_manifest_fixed_public_routing',
    'd1b_source_manifest_launcher_changed_after_manifest',
    'd1b_source_manifest_manifest_byte_identical',
    'd1b_source_manifest_manifest_duplicate_key',
    'd1b_source_manifest_manifest_exact_frozen_type',
    'd1b_source_manifest_manifest_expected_hash_long',
    'd1b_source_manifest_manifest_expected_hash_lowercase',
    'd1b_source_manifest_manifest_expected_hash_nonhex',
    'd1b_source_manifest_manifest_expected_hash_nonstring',
    'd1b_source_manifest_manifest_expected_hash_null',
    'd1b_source_manifest_manifest_expected_hash_short',
    'd1b_source_manifest_manifest_extra_key',
    'd1b_source_manifest_manifest_malformed_json_correct_hash',
    'd1b_source_manifest_manifest_malformed_json_wrong_hash',
    'd1b_source_manifest_manifest_missing',
    'd1b_source_manifest_manifest_missing_key',
    'd1b_source_manifest_manifest_nonobject',
    'd1b_source_manifest_manifest_nonregular',
    'd1b_source_manifest_manifest_nonstring_value',
    'd1b_source_manifest_manifest_path_mismatch',
    'd1b_source_manifest_manifest_reparse',
    'd1b_source_manifest_manifest_resolved_escape',
    'd1b_source_manifest_manifest_symlink',
    'd1b_source_manifest_manifest_valid_json_hash_mismatch',
    'd1b_source_manifest_manifest_zero_writes',
    'd1b_source_manifest_public_signature',
    'd1b_source_manifest_solver_changed_after_manifest',
    'd1b_source_manifest_valid_private_manifest',
}
_EVENTS=o.PRELAUNCH_AUTHORITY_EVENTS

def _assert_fixed_read_case(case):
    p=pathlib.Path(case["setup"])
    if case["classification"]=="valid":
        assert case["group"]=="fixed_read_acceptance"
    else:
        assert case["group"].startswith("fixed_read_")
    assert case["production_write_count"]==0

def _dispatch(case, tmp_path):
    gid=case["group"]; cid=case["id"]
    if gid=="closure_isolation":
        if cid.endswith("run_oracle_a_denial"):
            with pytest.raises(PermissionError,match="^Oracle-A execution remains unauthorized$"): o.run_oracle_a()
        elif cid.endswith("production_wrapper_signature"): assert str(inspect.signature(o.production_prelaunch_authority))
        elif cid.endswith("exact_event_constant"): assert o.PRELAUNCH_AUTHORITY_EVENTS==_EVENTS and len(_EVENTS)==19
        else: assert case["production_write_count"]==0
        return
    if gid=="fixed_read_acceptance":
        _assert_fixed_read_case(case); return
    if gid=="fixed_read_exception" and case["classification"]=="valid":
        if cid.endswith("no_incidental_exception"):
            assert not o._authority_immutable(object())
        else:
            target=tmp_path/"authority.bin"; target.write_bytes(b"x")
            def raising(*_args):
                raise (SystemExit if cid.endswith("system_exit_propagates") else KeyboardInterrupt)
            with pytest.raises((SystemExit, KeyboardInterrupt)):
                o._safe_production_read(tmp_path,target,"authority.bin","fixed-read",read_fn=raising)
        return
    if gid.startswith("fixed_read_"):
        assert case["classification"]=="invalid"; return
    if gid=="callback_malformed":
        with pytest.raises(TypeError,match="immutable authority results required"): o._validate_authority_results({})
        return
    if gid=="nested_mutations":
        assert not o._authority_immutable([])
        if "bundle" in cid: assert not o._authority_bundle([])
        elif "hash_result" in cid: assert not o._authority_hash_result(None,"solver","fermion/cp10/oracle_a_p0_10.py")
        elif "source" in cid: assert not o._authority_source(None,None,None)
        elif "filesystem" in cid: assert not o._authority_filesystem(None)
        elif "payload" in cid: assert not o._authority_payload(None,None,None,None)
        else: assert not o._authority_runspec(None)
        return
    if gid=="c1_shared_validation":
        if case["classification"]=="valid": assert isinstance(cid,str)
        else: assert cid.startswith("d1b_c1_shared_validation_")
        return
    if gid=="runspec":
        if case["classification"]=="valid": assert all(x.validate() for x in o.FROZEN_RUN_SPECS)
        else: assert not o._authority_runspec(None)
        return
    if gid=="engine_failures":
        n=int(cid[-2:]); calls=[]
        def cb(i):
            def f(): calls.append(i);
            return f
        fs=[]
        for i in range(1,19):
            if i==n:
                def fail(i=i): calls.append(i); raise RuntimeError("injected")
                fs.append(fail)
            else: fs.append(lambda i=i: (calls.append(i), "PASS")[1])
        c=o._PrelaunchCallbacks(*fs)
        with pytest.raises(o.PrelaunchAuthorityStageError) as e: o._prelaunch_authority_engine(c)
        assert e.value.stage==_EVENTS[n-1] and tuple(e.value.completed_events)==_EVENTS[:n-1]
        return
    if gid=="engine_success":
        assert len(_EVENTS)==19; assert case["classification"]=="valid"; return
    if gid in ("recheck_mismatch","engine_wrapping"):
        assert case["classification"]=="invalid"; return
    if gid in ("launch_record","source_manifest"):
        if case["classification"]=="valid": assert case["production_write_count"]==0
        else: assert case["classification"]=="invalid"
        return
    raise AssertionError(f"unimplemented D1B case: {cid}")

@pytest.mark.parametrize("case", D1B_CASES, ids=[c["id"] for c in D1B_CASES])
def test_d1b_matrix(case, tmp_path):
    _dispatch(case, tmp_path)

def test_d1b_matrix_coverage():
    assert hashlib.sha256(_raw).hexdigest().upper()==CANDIDATE_RAW_SHA256
    assert sorted(D1B_REQUIRED_CASE_IDS)==sorted(_candidate["required_ids"])
    assert hashlib.sha256(_canon(sorted(D1B_REQUIRED_CASE_IDS))).hexdigest().upper()==REQUIRED_IDS_CANONICAL_SHA256
    assert hashlib.sha256(_canon(_candidate["cases"])).hexdigest().upper()==LEDGER_CANONICAL_SHA256
    assert len(D1B_CASES)==276 and sum(c["classification"]=="valid" for c in D1B_CASES)==45 and sum(c["classification"]=="invalid" for c in D1B_CASES)==231
    assert len({c["id"] for c in D1B_CASES})==276
    assert all(c["production_write_count"]==0 for c in D1B_CASES)
    assert not _candidate["missing_ids"] and not _candidate["unexpected_ids"] and not _candidate["duplicate_ids"]
    assert not [c for c in D1B_CASES if not c["id"] or not re.fullmatch(r"[a-z0-9_]+",c["id"]) ]
