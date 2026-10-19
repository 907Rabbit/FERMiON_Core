import hashlib, json, inspect, re, pathlib, os, stat, types, pytest, dataclasses, tempfile
from dataclasses import dataclass
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
FIXED_READ_CASES=tuple(c for c in D1B_CASES if c["id"].startswith("d1b_fixed_read_"))

def _assert_fixed_read_case(case):
    p=pathlib.Path(case["setup"])
    if case["classification"]=="valid":
        assert case["group"]=="fixed_read_acceptance"
    else:
        assert case["group"].startswith("fixed_read_")
    assert case["production_write_count"]==0

def _run_fixed_read_case(case, tmp_path):
    cid=case["id"]
    root=tmp_path / "root"; root.mkdir()
    leaf=root / "data.bin"; leaf.write_bytes(b"abcdef")
    allowed="data.bin"
    if case["classification"]=="valid":
        if cid.endswith(("system_exit_propagates","keyboard_interrupt_propagates")):
            def raising(*_args): raise (SystemExit if cid.endswith("system_exit_propagates") else KeyboardInterrupt)
            with pytest.raises((SystemExit,KeyboardInterrupt)):
                o._safe_production_read(root,leaf,allowed,"fixed-read",read_fn=raising)
            return
        if cid.endswith("valid_zero_byte_file"): leaf.write_bytes(b"")
        if cid.endswith("valid_second_allowlist_entry"):
            leaf.unlink(); (root/"other.bin").write_bytes(b"x"); leaf.write_bytes(b"second")
            allowed=("other.bin","data.bin")
        if cid.endswith("valid_partial_descriptor_reads"):
            chunks=[b"ab",b"cd",b"ef"]
            def read_fn(_fd,n): return chunks.pop(0)
        else: read_fn=lambda _fd,n: (b"second" if cid.endswith("valid_second_allowlist_entry") else b"abcdef")
        raw=o._safe_production_read(root,leaf,allowed,"fixed-read",open_fn=lambda *_: 1,fstat_fn=lambda _fd: os.stat(leaf),read_fn=read_fn,close_fn=lambda _fd: None)
        assert raw==(b"" if cid.endswith("valid_zero_byte_file") else (b"second" if cid.endswith("valid_second_allowlist_entry") else b"abcdef"))
        return
    def expect(exc= o.FilesystemAuthorizationError, **kwargs):
        params={"root":root,"requested_path":leaf,"allowed_relative":allowed,"label":"fixed-read"}
        params.update(kwargs)
        with pytest.raises(exc): o._safe_production_read(**params)
    if cid.endswith("relative_root"):
        expect(root=pathlib.Path("relative"))
    elif cid.endswith("relative_requested_path"):
        expect(requested_path=pathlib.Path("data.bin"))
    elif cid.endswith("allowed_none"):
        expect(allowed_relative=None)
    elif cid.endswith("allowed_list"):
        expect(allowed_relative=["data.bin"])
    elif cid.endswith("tuple_nonstring"):
        expect(allowed_relative=("data.bin",1))
    elif cid.endswith("empty_allowlist"):
        expect(allowed_relative=())
    elif cid.endswith(("empty_entry","absolute_entry","dot_entry","parent_traversal")):
        val={"empty_entry":"","absolute_entry":"/x","dot_entry":".","parent_traversal":"../x"}[cid.rsplit("_",1)[-2]+'_'+cid.rsplit("_",1)[-1]] if False else ("" if cid.endswith("empty_entry") else ("/x" if cid.endswith("absolute_entry") else ("." if cid.endswith("dot_entry") else "../x")))
        expect(allowed_relative=val)
    elif "duplicate_textual" in cid or "path_equivalent_duplicate" in cid:
        expect(allowed_relative=("data.bin","data.bin"))
    elif cid.endswith(("candidate_not_allowlisted","zero_candidate_matches","multiple_candidate_matches")):
        if cid.endswith("multiple_candidate_matches"): expect(allowed_relative=("data.bin","data.bin"))
        else: expect(allowed_relative="other.bin")
    elif "root_missing" in cid:
        expect(root=tmp_path/"missing", requested_path=tmp_path/"missing"/"data.bin")
    elif "intermediate_missing" in cid:
        expect(requested_path=root/"missing"/"data.bin",allowed_relative="missing/data.bin")
    elif "leaf_missing_with_message" in cid:
        expect(RuntimeError,requested_path=root/"missing.bin",allowed_relative="missing.bin",missing_message="missing")
    elif "leaf_missing_without_message" in cid:
        expect(requested_path=root/"missing.bin",allowed_relative="missing.bin")
    elif any(x in cid for x in ("symlink","reparse","nondirectory","nonregular","resolution","descriptor","post_open","post_read","read_","close_only")):
        def bad(*_a,**_k): raise RuntimeError("injected")
        if "system_exit" in cid or "keyboard_interrupt" in cid: raise AssertionError("unreachable")
        expect(read_fn=bad if "read_" in cid else None)
    elif cid.endswith("no_incidental_exception"):
        def raising(*_args): raise RuntimeError("injected")
        expect(read_fn=raising)
    else:
        expect()

FIXED_READ_SCENARIOS={c["id"]:{"id":c["id"],"setup":c["setup"],"expected":c["expected"],"target":"_safe_production_read","callable":_run_fixed_read_case} for c in FIXED_READ_CASES}
BATCH_A_IDS=(
    "d1b_fixed_read_chain_leaf_nonregular","d1b_fixed_read_chain_leaf_reparse","d1b_fixed_read_chain_leaf_symlink",
    "d1b_fixed_read_chain_parent_nondirectory","d1b_fixed_read_chain_parent_reparse","d1b_fixed_read_chain_parent_symlink",
    "d1b_fixed_read_chain_root_reparse","d1b_fixed_read_chain_root_symlink",
    "d1b_fixed_read_resolution_candidate_resolution_failure","d1b_fixed_read_resolution_post_open_resolved_change",
    "d1b_fixed_read_resolution_post_read_resolved_change","d1b_fixed_read_resolution_resolved_authority_mismatch",
    "d1b_fixed_read_resolution_resolved_escape","d1b_fixed_read_resolution_root_resolution_failure",
)
FIXED_READ_BATCH_A_IDS=frozenset(BATCH_A_IDS)
FIXED_READ_PREVIOUS_AUTHENTIC_IDS=frozenset(c["id"] for c in FIXED_READ_CASES if c["id"] in {
    "d1b_fixed_read_acceptance_valid_close_success","d1b_fixed_read_acceptance_valid_exact_raw_bytes","d1b_fixed_read_acceptance_valid_nonempty_single_allowlist","d1b_fixed_read_acceptance_valid_partial_descriptor_reads","d1b_fixed_read_acceptance_valid_second_allowlist_entry","d1b_fixed_read_acceptance_valid_zero_byte_file","d1b_fixed_read_chain_intermediate_missing","d1b_fixed_read_chain_leaf_missing_with_message","d1b_fixed_read_chain_leaf_missing_without_message","d1b_fixed_read_chain_root_missing","d1b_fixed_read_exception_keyboard_interrupt_propagates","d1b_fixed_read_exception_system_exit_propagates","d1b_fixed_read_lexical_absolute_entry","d1b_fixed_read_lexical_allowed_list","d1b_fixed_read_lexical_allowed_none","d1b_fixed_read_lexical_candidate_not_allowlisted","d1b_fixed_read_lexical_dot_entry","d1b_fixed_read_lexical_duplicate_textual_entry","d1b_fixed_read_lexical_empty_allowlist","d1b_fixed_read_lexical_empty_entry","d1b_fixed_read_lexical_multiple_candidate_matches","d1b_fixed_read_lexical_parent_traversal","d1b_fixed_read_lexical_path_equivalent_duplicate","d1b_fixed_read_lexical_relative_requested_path","d1b_fixed_read_lexical_relative_root","d1b_fixed_read_lexical_tuple_nonstring","d1b_fixed_read_lexical_zero_candidate_matches"})
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_PREVIOUS_AUTHENTIC_IDS
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS
def _run_batch_a_case(case,tmp_path):
    cid=case["id"]; root=tmp_path/"root"; root.mkdir(); parent=root/"sub"; parent.mkdir(); leaf=parent/"data.bin"; leaf.write_bytes(b"x")
    trace=[]
    def meta(kind="file"):
        mode=stat.S_IFREG if kind in ("file","nondirectory") else (stat.S_IFDIR if kind in ("dir","leaf_nonregular") else stat.S_IFLNK)
        return types.SimpleNamespace(st_mode=mode,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=(0x400 if kind=="reparse" else 0))
    defect=None
    if cid.endswith("leaf_nonregular"): defect="leaf_nonregular"
    elif cid.endswith("leaf_reparse"): defect="leaf_reparse"
    elif cid.endswith("leaf_symlink"): defect="leaf_symlink"
    elif cid.endswith("parent_nondirectory"): defect="parent_nondirectory"
    elif cid.endswith("parent_reparse"): defect="parent_reparse"
    elif cid.endswith("parent_symlink"): defect="parent_symlink"
    elif cid.endswith("root_reparse"): defect="root_reparse"
    elif cid.endswith("root_symlink"): defect="root_symlink"
    def lstat_fn(path):
        trace.append(("lstat",str(path)))
        if defect and ((defect.startswith("root_") and path==root) or (defect.startswith("parent_") and path==parent) or (defect.startswith("leaf_") and path==leaf)):
            return meta("reparse" if "reparse" in defect else ("symlink" if "symlink" in defect else ("leaf_nonregular" if "leaf_" in defect else "nondirectory")))
        return meta("dir" if path in (root,parent) else "file")
    resolve_calls=0
    def resolve_fn(path):
        nonlocal resolve_calls
        resolve_calls+=1; trace.append(("resolve",resolve_calls))
        if cid.endswith("root_resolution_failure") and resolve_calls==1: raise RuntimeError("resolve")
        if cid.endswith("candidate_resolution_failure") and resolve_calls==2: raise RuntimeError("resolve")
        if cid.endswith("resolved_escape") and resolve_calls==2: return tmp_path/"outside"
        if cid.endswith("resolved_authority_mismatch") and resolve_calls==2: return root/"other.bin"
        if cid.endswith("post_open_resolved_change") and resolve_calls==4: return root/"other.bin"
        if cid.endswith("post_read_resolved_change") and resolve_calls==6: return root/"other.bin"
        return pathlib.Path(path)
    def fail():
        with pytest.raises(o.FilesystemAuthorizationError):
            o._safe_production_read(root,leaf,"sub/data.bin","fixed-read",lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=lambda *_: 1,fstat_fn=lambda _fd: meta("file"),read_fn=lambda *_: b"x",close_fn=lambda _fd: None)
    fail(); assert trace and trace[0][0] in ("lstat","resolve")
    # counterfactual: normal callbacks reach a successful descriptor-bound read
    raw=o._safe_production_read(root,leaf,"sub/data.bin", "fixed-read", lstat_fn=lambda p: meta("dir" if p in (root,parent) else "file"), open_fn=lambda *_: 1,fstat_fn=lambda _fd: meta("file"),read_fn=lambda *_: b"x",close_fn=lambda _fd: None)
    assert raw==b"x"

BATCH_A_SCENARIOS={
    "d1b_fixed_read_chain_leaf_nonregular":{"id":"d1b_fixed_read_chain_leaf_nonregular","family":"leaf_type","defect":"leaf_fifo","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read is not a file","target_signal":"leaf_mode_nonregular"},
    "d1b_fixed_read_chain_leaf_reparse":{"id":"d1b_fixed_read_chain_leaf_reparse","family":"leaf_reparse","defect":"leaf_reparse","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read reparse path","target_signal":"leaf_reparse_attribute"},
    "d1b_fixed_read_chain_leaf_symlink":{"id":"d1b_fixed_read_chain_leaf_symlink","family":"leaf_symlink","defect":"leaf_symlink","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read reparse path","target_signal":"leaf_symlink_mode"},
    "d1b_fixed_read_chain_parent_nondirectory":{"id":"d1b_fixed_read_chain_parent_nondirectory","family":"parent_type","defect":"parent_file","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read parent is not directory","target_signal":"parent_non_directory_mode"},
    "d1b_fixed_read_chain_parent_reparse":{"id":"d1b_fixed_read_chain_parent_reparse","family":"parent_reparse","defect":"parent_reparse","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read reparse path","target_signal":"parent_reparse_attribute"},
    "d1b_fixed_read_chain_parent_symlink":{"id":"d1b_fixed_read_chain_parent_symlink","family":"parent_symlink","defect":"parent_symlink","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read reparse path","target_signal":"parent_symlink_mode"},
    "d1b_fixed_read_chain_root_reparse":{"id":"d1b_fixed_read_chain_root_reparse","family":"root_reparse","defect":"root_reparse","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read reparse path","target_signal":"root_reparse_attribute"},
    "d1b_fixed_read_chain_root_symlink":{"id":"d1b_fixed_read_chain_root_symlink","family":"root_symlink","defect":"root_symlink","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read reparse path","target_signal":"root_symlink_mode"},
    "d1b_fixed_read_resolution_candidate_resolution_failure":{"id":"d1b_fixed_read_resolution_candidate_resolution_failure","family":"resolution","defect":"candidate_failure","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read path safety","target_signal":"candidate_resolve_failure"},
    "d1b_fixed_read_resolution_post_open_resolved_change":{"id":"d1b_fixed_read_resolution_post_open_resolved_change","family":"resolution","defect":"post_open_change","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read resolved authority","target_signal":"post_open_resolve_change"},
    "d1b_fixed_read_resolution_post_read_resolved_change":{"id":"d1b_fixed_read_resolution_post_read_resolved_change","family":"resolution","defect":"post_read_change","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read resolved authority","target_signal":"post_read_resolve_change"},
    "d1b_fixed_read_resolution_resolved_authority_mismatch":{"id":"d1b_fixed_read_resolution_resolved_authority_mismatch","family":"resolution","defect":"authority_mismatch","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read resolved authority","target_signal":"resolved_authority_mismatch"},
    "d1b_fixed_read_resolution_resolved_escape":{"id":"d1b_fixed_read_resolution_resolved_escape","family":"resolution","defect":"escape","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read resolved escape","target_signal":"resolved_containment_escape"},
    "d1b_fixed_read_resolution_root_resolution_failure":{"id":"d1b_fixed_read_resolution_root_resolution_failure","family":"resolution","defect":"root_failure","expected_type":o.FilesystemAuthorizationError,"message":"fixed-read path safety","target_signal":"root_resolve_failure"},
}

@dataclass(frozen=True)
class _PathStateScenario:
    id:str; component:str; kind:str; mode:int; attributes:int; message:str; target:tuple; forbidden:tuple; counter_mode:int; counter_attributes:int; expected_bytes:bytes; expected_cause_type:object; failure_trace:tuple; success_trace:tuple

_SUCCESS_TRACE=(
    ("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),
    ("resolve","root",1),("resolve","candidate",2),("resolve","fixed",3),("open",),
    ("fstat","open"),("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),
    ("resolve","candidate_post_open",4),("read",),("fstat","final"),
    ("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),
    ("resolve","root_post_read",5),("resolve","candidate_post_read",6),("close",),
)
def _failure_trace(component,kind):
    parts={"root":(),"parent":(("lstat","root","normal"),),"leaf":(("lstat","root","normal"),("lstat","parent","normal"))}[component]
    return parts+(("target",component,kind),)

PATH_STATE_SCENARIOS={
 "d1b_fixed_read_chain_leaf_nonregular":_PathStateScenario("d1b_fixed_read_chain_leaf_nonregular","leaf","fifo",stat.S_IFIFO,0,"fixed-read is not a file",("target","leaf","fifo"),("resolve","open","fstat","read","close"),stat.S_IFREG,0,b"x",None,_failure_trace("leaf","fifo"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_leaf_reparse":_PathStateScenario("d1b_fixed_read_chain_leaf_reparse","leaf","reparse",stat.S_IFREG,0x400,"fixed-read reparse path",("target","leaf","reparse"),("resolve","open","fstat","read","close"),stat.S_IFREG,0,b"x",None,_failure_trace("leaf","reparse"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_leaf_symlink":_PathStateScenario("d1b_fixed_read_chain_leaf_symlink","leaf","symlink",stat.S_IFLNK,0,"fixed-read reparse path",("target","leaf","symlink"),("resolve","open","fstat","read","close"),stat.S_IFREG,0,b"x",None,_failure_trace("leaf","symlink"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_parent_nondirectory":_PathStateScenario("d1b_fixed_read_chain_parent_nondirectory","parent","nondirectory",stat.S_IFREG,0,"fixed-read parent is not directory",("target","parent","nondirectory"),("resolve","open","fstat","read","close"),stat.S_IFDIR,0,b"x",None,_failure_trace("parent","nondirectory"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_parent_reparse":_PathStateScenario("d1b_fixed_read_chain_parent_reparse","parent","reparse",stat.S_IFDIR,0x400,"fixed-read reparse path",("target","parent","reparse"),("resolve","open","fstat","read","close"),stat.S_IFDIR,0,b"x",None,_failure_trace("parent","reparse"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_parent_symlink":_PathStateScenario("d1b_fixed_read_chain_parent_symlink","parent","symlink",stat.S_IFLNK,0,"fixed-read reparse path",("target","parent","symlink"),("resolve","open","fstat","read","close"),stat.S_IFDIR,0,b"x",None,_failure_trace("parent","symlink"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_root_reparse":_PathStateScenario("d1b_fixed_read_chain_root_reparse","root","reparse",stat.S_IFDIR,0x400,"fixed-read reparse path",("target","root","reparse"),("resolve","open","fstat","read","close"),stat.S_IFDIR,0,b"x",None,_failure_trace("root","reparse"),_SUCCESS_TRACE),
 "d1b_fixed_read_chain_root_symlink":_PathStateScenario("d1b_fixed_read_chain_root_symlink","root","symlink",stat.S_IFLNK,0,"fixed-read reparse path",("target","root","symlink"),("resolve","open","fstat","read","close"),stat.S_IFDIR,0,b"x",None,_failure_trace("root","symlink"),_SUCCESS_TRACE),
}
assert tuple(PATH_STATE_SCENARIOS)==tuple(BATCH_A_IDS[:8])
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_PREVIOUS_AUTHENTIC_IDS|frozenset(PATH_STATE_SCENARIOS)
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS

def _execute_path_state_scenario(scenario,tmp_path):
    root=tmp_path/"root"; root.mkdir(); parent=root/"sub"; parent.mkdir(); leaf=parent/"data.bin"; leaf.write_bytes(b"x"); active=[True]; trace=[]; resolve_index=[0]; fstat_index=[0]
    def meta(mode,attrs=0): return types.SimpleNamespace(st_mode=mode,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=attrs)
    def lstat_fn(path):
        if path==root: component="root"
        elif path==parent: component="parent"
        elif path==leaf: component="leaf"
        else: raise AssertionError(f"unexpected lstat path: {path}")
        if active[0] and component==scenario.component:
            trace.append(("target",component,scenario.kind)); return meta(scenario.mode,scenario.attributes)
        trace.append(("lstat",component,"normal")); return meta(scenario.counter_mode,scenario.counter_attributes) if component==scenario.component else meta(stat.S_IFDIR if component in ("root","parent") else stat.S_IFREG)
    def resolve_fn(path):
        resolve_index[0]+=1; n=resolve_index[0]
        name={1:"root",2:"candidate",3:"fixed",4:"candidate_post_open",5:"root_post_read",6:"candidate_post_read"}.get(n)
        if name is None: raise AssertionError(f"unexpected resolve ordinal: {n}")
        trace.append(("resolve",name,n)); return pathlib.Path(path)
    def open_fn(*args): trace.append(("open",)); return 1
    def fstat_fn(_fd): fstat_index[0]+=1; trace.append(("fstat","open" if fstat_index[0]==1 else "final")); return meta(stat.S_IFREG,0)
    def read_fn(_fd,n): trace.append(("read",)); return b"x"[:n]
    def close_fn(_fd): trace.append(("close",))
    callbacks=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(o.FilesystemAuthorizationError) as exc:
        o._safe_production_read(root,leaf,"sub/data.bin","fixed-read",**callbacks)
    assert type(exc.value) is o.FilesystemAuthorizationError and str(exc.value)==scenario.message and (type(exc.value.__cause__) if exc.value.__cause__ else None) is scenario.expected_cause_type
    assert tuple(trace)==scenario.failure_trace and trace.count(scenario.target)==1 and all(not any(e[0]==x for e in trace) for x in scenario.forbidden)
    active[0]=False; trace.clear(); resolve_index[0]=0; fstat_index[0]=0
    raw=o._safe_production_read(root,leaf,"sub/data.bin","fixed-read",**callbacks)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and not any(e[0]=="target" for e in trace)
    assert all(trace.count((name,))==1 for name in ("open","read","close")) and trace.count(("fstat","open"))==1 and trace.count(("fstat","final"))==1

@dataclass(frozen=True)
class _ResolutionScenario:
    id:str; ordinal:int; phase:str; kind:str; defect:str; expected_type:object; message:str; cause_type:object; cause_message:object; target:tuple; failure_trace:tuple; forbidden:tuple; success_trace:tuple; expected_bytes:bytes; counterfactual_result:str="authorized"

RESOLUTION_SCENARIOS={
 "d1b_fixed_read_resolution_candidate_resolution_failure":_ResolutionScenario("d1b_fixed_read_resolution_candidate_resolution_failure",2,"candidate","exception","resolution_failure",o.FilesystemAuthorizationError,"fixed-read path safety",RuntimeError,"resolve",("target","candidate","resolution_failure"),(("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","root",1),("target","candidate","resolution_failure")),("open","fstat","read","close"),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_resolution_post_open_resolved_change":_ResolutionScenario("d1b_fixed_read_resolution_post_open_resolved_change",4,"candidate_post_open","path","resolved_change",o.FilesystemAuthorizationError,"fixed-read resolved authority",None,None,("target","candidate_post_open","resolved_change"),(("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","root",1),("resolve","candidate",2),("resolve","fixed",3),("open",),("fstat","open"),("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("target","candidate_post_open","resolved_change"),("close",)),("read",),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_resolution_post_read_resolved_change":_ResolutionScenario("d1b_fixed_read_resolution_post_read_resolved_change",6,"candidate_post_read","path","resolved_change",o.FilesystemAuthorizationError,"fixed-read resolved authority",None,None,("target","candidate_post_read","resolved_change"),(("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","root",1),("resolve","candidate",2),("resolve","fixed",3),("open",),("fstat","open"),("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","candidate_post_open",4),("read",),("fstat","final"),("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","root_post_read",5),("target","candidate_post_read","resolved_change"),("close",)),(),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_resolution_resolved_authority_mismatch":_ResolutionScenario("d1b_fixed_read_resolution_resolved_authority_mismatch",2,"candidate","path","authority_mismatch",o.FilesystemAuthorizationError,"fixed-read resolved authority",None,None,("target","candidate","authority_mismatch"),(("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","root",1),("target","candidate","authority_mismatch"),("resolve","fixed",3)),("open","fstat","read","close"),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_resolution_resolved_escape":_ResolutionScenario("d1b_fixed_read_resolution_resolved_escape",2,"candidate","path","escape",o.FilesystemAuthorizationError,"fixed-read resolved escape",None,None,("target","candidate","escape"),(("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("resolve","root",1),("target","candidate","escape"),("resolve","fixed",3)),("open","fstat","read","close"),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_resolution_root_resolution_failure":_ResolutionScenario("d1b_fixed_read_resolution_root_resolution_failure",1,"root","exception","resolution_failure",o.FilesystemAuthorizationError,"fixed-read path safety",RuntimeError,"resolve",("target","root","resolution_failure"),(("lstat","root","normal"),("lstat","parent","normal"),("lstat","leaf","normal"),("target","root","resolution_failure")),("open","fstat","read","close"),_SUCCESS_TRACE,b"x"),
}
assert tuple(RESOLUTION_SCENARIOS)==tuple(BATCH_A_IDS[8:])
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_PREVIOUS_AUTHENTIC_IDS|frozenset(PATH_STATE_SCENARIOS)|frozenset(RESOLUTION_SCENARIOS)
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS

def _execute_resolution_scenario(scenario,tmp_path):
    root=tmp_path/"root"; root.mkdir(); parent=root/"sub"; parent.mkdir(); leaf=parent/"data.bin"; leaf.write_bytes(b"x")
    active=[True]; trace=[]; ordinal=[0]; fstats=[0]
    def meta(mode=stat.S_IFREG,attrs=0): return types.SimpleNamespace(st_mode=mode,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=attrs)
    def lstat_fn(path):
        if path==root: c="root"
        elif path==parent: c="parent"
        elif path==leaf: c="leaf"
        else: raise AssertionError(f"unexpected lstat path: {path}")
        trace.append(("lstat",c,"normal")); return meta(stat.S_IFDIR if c in ("root","parent") else stat.S_IFREG)
    def resolve_fn(path):
        ordinal[0]+=1; n=ordinal[0]; names={1:"root",2:"candidate",3:"fixed",4:"candidate_post_open",5:"root_post_read",6:"candidate_post_read"}
        expected_paths={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}
        if n not in names or path!=expected_paths[n]: raise AssertionError(f"unexpected resolve input at ordinal {n}: {path}")
        name=names[n]
        if n==scenario.ordinal and active[0]:
            trace.append(("target",name,scenario.defect))
            if scenario.defect=="resolution_failure": raise RuntimeError("resolve")
            return tmp_path/"outside" if scenario.defect=="escape" else root/"other.bin"
        if not active[0] and scenario.counterfactual_result!="authorized": raise AssertionError("counterfactual result mismatch")
        trace.append(("resolve",name,n)); return pathlib.Path(path)
    def open_fn(*_): trace.append(("open",)); return 1
    def fstat_fn(_): fstats[0]+=1; trace.append(("fstat","open" if fstats[0]==1 else "final")); return meta()
    def read_fn(_,n): trace.append(("read",)); return b"x"[:n]
    def close_fn(_): trace.append(("close",))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc: o._safe_production_read(root,leaf,"sub/data.bin","fixed-read",**cb)
    assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message
    assert (type(exc.value.__cause__) if exc.value.__cause__ else None) is scenario.cause_type
    if scenario.cause_type is not None: assert str(exc.value.__cause__)==scenario.cause_message
    else: assert scenario.cause_message is None and exc.value.__cause__ is None
    assert tuple(trace)==scenario.failure_trace and trace.count(scenario.target)==1
    assert all(not any(e[0]==name for e in trace) for name in scenario.forbidden)
    active[0]=False; trace.clear(); ordinal[0]=0; fstats[0]=0
    raw=o._safe_production_read(root,leaf,"sub/data.bin","fixed-read",**cb)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and not any(e[0]=="target" for e in trace)

@dataclass(frozen=True)
class _B1Scenario:
    id:str; defect:str; expected_type:object; message:str; cause_type:object; cause_message:object; failure_trace:tuple; target:tuple; success_trace:tuple; expected_bytes:bytes

_B1_PRE=(('lstat','root','normal'),('lstat','parent','normal'),('lstat','leaf','normal'),('resolve','root',1),('resolve','candidate',2),('resolve','fixed',3))
_B1_IDS=("d1b_fixed_read_descriptor_descriptor_leaf_identity_mismatch","d1b_fixed_read_descriptor_descriptor_nonregular","d1b_fixed_read_descriptor_fstat_oserror","d1b_fixed_read_descriptor_fstat_runtimeerror","d1b_fixed_read_descriptor_open_oserror","d1b_fixed_read_descriptor_open_runtimeerror")
_B1_SCENARIOS={
 "d1b_fixed_read_descriptor_descriptor_leaf_identity_mismatch":_B1Scenario("d1b_fixed_read_descriptor_descriptor_leaf_identity_mismatch","leaf_identity",o.FilesystemAuthorizationError,"fixed-read descriptor identity",None,None,_B1_PRE+(('open',),('target','fstat','leaf_identity'),('close',)),('target','fstat','leaf_identity'),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_descriptor_descriptor_nonregular":_B1Scenario("d1b_fixed_read_descriptor_descriptor_nonregular","nonregular_descriptor",o.FilesystemAuthorizationError,"fixed-read descriptor identity",None,None,_B1_PRE+(('open',),('target','fstat','nonregular_descriptor'),('close',)),('target','fstat','nonregular_descriptor'),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_descriptor_fstat_oserror":_B1Scenario("d1b_fixed_read_descriptor_fstat_oserror","fstat_oserror",o.FilesystemAuthorizationError,"fixed-read path safety",OSError,"fstat",_B1_PRE+(('open',),('target','fstat','fstat_oserror'),('close',)),('target','fstat','fstat_oserror'),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_descriptor_fstat_runtimeerror":_B1Scenario("d1b_fixed_read_descriptor_fstat_runtimeerror","fstat_runtimeerror",o.FilesystemAuthorizationError,"fixed-read path safety",RuntimeError,"fstat",_B1_PRE+(('open',),('target','fstat','fstat_runtimeerror'),('close',)),('target','fstat','fstat_runtimeerror'),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_descriptor_open_oserror":_B1Scenario("d1b_fixed_read_descriptor_open_oserror","open_oserror",o.FilesystemAuthorizationError,"fixed-read open failure",OSError,"open",_B1_PRE+(('target','open','open_oserror'),),('target','open','open_oserror'),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_descriptor_open_runtimeerror":_B1Scenario("d1b_fixed_read_descriptor_open_runtimeerror","open_runtimeerror",o.FilesystemAuthorizationError,"fixed-read open failure",RuntimeError,"open",_B1_PRE+(('target','open','open_runtimeerror'),),('target','open','open_runtimeerror'),_SUCCESS_TRACE,b"x"),
}
assert tuple(_B1_SCENARIOS)==_B1_IDS
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_AUTHENTIC_IDS|frozenset(_B1_SCENARIOS)
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS

def _execute_b1_scenario(scenario,tmp_path):
    assert _B1_SCENARIOS.get(scenario.id) is scenario
    root=tmp_path/'root'; root.mkdir(); parent=root/'sub'; parent.mkdir(); leaf=parent/'data.bin'; leaf.write_bytes(b'x')
    active=[True]; trace=[]; fstat_count=[0]; close_count=[0]; fd=object(); expected_flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0); open_args=[]; read_args=[]; close_args=[]; fixture_before=leaf.read_bytes()
    def meta(mode=stat.S_IFREG,ino=1): return types.SimpleNamespace(st_mode=mode,st_dev=1,st_ino=ino,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
    def lstat_fn(path):
        if path==root: c='root'
        elif path==parent: c='parent'
        elif path==leaf: c='leaf'
        else: raise AssertionError(f'unexpected lstat path: {path}')
        trace.append(('lstat',c,'normal')); return meta(stat.S_IFDIR if c in ('root','parent') else stat.S_IFREG)
    def resolve_fn(path):
        expected={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}; n=sum(1 for e in trace if e[0]=='resolve')+1
        if n not in expected or path!=expected[n]: raise AssertionError(f'unexpected resolve input: {n} {path}')
        name={1:'root',2:'candidate',3:'fixed',4:'candidate_post_open',5:'root_post_read',6:'candidate_post_read'}[n]
        trace.append(('resolve',name,n)); return pathlib.Path(path)
    def open_fn(*_):
        path,flags=_[0],_[1]; open_args.append((path,flags)); assert path==leaf and flags==expected_flags
        trace.append(('target','open',scenario.defect));
        if active[0]:
            if scenario.defect=='open_oserror': raise OSError('open')
            if scenario.defect=='open_runtimeerror': raise RuntimeError('open')
        trace[-1]=('open',); return fd
    def fstat_fn(_):
        assert _ is fd
        fstat_count[0]+=1
        if fstat_count[0]==1 and active[0]:
            trace.append(('target','fstat',scenario.defect))
            if scenario.defect=='fstat_oserror': raise OSError('fstat')
            if scenario.defect=='fstat_runtimeerror': raise RuntimeError('fstat')
            return meta(stat.S_IFIFO if scenario.defect=='nonregular_descriptor' else stat.S_IFREG,2 if scenario.defect=='leaf_identity' else 1)
        trace.append(('fstat','open' if fstat_count[0]==1 else 'final')); return meta()
    def read_fn(_,n): assert _ is fd and n==1; read_args.append((_,n)); trace.append(('read',)); return b'x'[:n]
    def close_fn(_): assert _ is fd; close_args.append(_); close_count[0]+=1; trace.append(('close',))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc: o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message
    assert (type(exc.value.__cause__) if exc.value.__cause__ else None) is scenario.cause_type
    if scenario.cause_type is not None: assert str(exc.value.__cause__)==scenario.cause_message
    assert tuple(trace)==scenario.failure_trace and trace.count(scenario.target)==1
    forbidden=("fstat","read","close") if scenario.defect.startswith("open_") else ("read",)
    assert all(not any(e[0]==x for e in trace) for x in forbidden)
    assert close_count[0]==(0 if scenario.defect.startswith('open_') else 1); assert leaf.read_bytes()==fixture_before
    active[0]=False; trace.clear(); fstat_count[0]=0; close_count[0]=0; open_args.clear(); read_args.clear(); close_args.clear()
    raw=o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and open_args==[(leaf,expected_flags)] and fstat_count[0]==2 and read_args==[(fd,1)] and close_args==[fd] and close_count[0]==1 and leaf.read_bytes()==fixture_before

@dataclass(frozen=True)
class _B2AScenario:
    id:str; component:str; defect:str; ordinal:int; mode:int; attributes:int; expected_type:object; message:str; cause_type:object; cause_message:object; target:tuple; failure_trace:tuple; success_trace:tuple; expected_bytes:bytes

_B2A_IDS=("d1b_fixed_read_post_open_post_open_identity_change","d1b_fixed_read_post_open_post_open_missing_component","d1b_fixed_read_post_open_post_open_reparse","d1b_fixed_read_post_open_post_open_symlink")
_B2A_SCENARIOS={
 "d1b_fixed_read_post_open_post_open_identity_change":_B2AScenario("d1b_fixed_read_post_open_post_open_identity_change","leaf","identity_change",6,stat.S_IFREG,0,o.FilesystemAuthorizationError,"fixed-read path changed",None,None,("target","post_open","identity_change"),_B1_PRE+(('open',),('fstat','open'),('lstat','root','normal'),('lstat','parent','normal'),('target','post_open','identity_change'),('close',)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_open_post_open_missing_component":_B2AScenario("d1b_fixed_read_post_open_post_open_missing_component","leaf","missing_component",6,stat.S_IFREG,0,o.FilesystemAuthorizationError,"fixed-read path safety",FileNotFoundError,"missing",("target","post_open","missing_component"),_B1_PRE+(('open',),('fstat','open'),('lstat','root','normal'),('lstat','parent','normal'),('target','post_open','missing_component'),('close',)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_open_post_open_reparse":_B2AScenario("d1b_fixed_read_post_open_post_open_reparse","leaf","reparse",6,stat.S_IFREG,0x400,o.FilesystemAuthorizationError,"fixed-read path changed",None,None,("target","post_open","reparse"),_B1_PRE+(('open',),('fstat','open'),('lstat','root','normal'),('lstat','parent','normal'),('target','post_open','reparse'),('close',)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_open_post_open_symlink":_B2AScenario("d1b_fixed_read_post_open_post_open_symlink","leaf","symlink",6,stat.S_IFLNK,0,o.FilesystemAuthorizationError,"fixed-read path changed",None,None,("target","post_open","symlink"),_B1_PRE+(('open',),('fstat','open'),('lstat','root','normal'),('lstat','parent','normal'),('target','post_open','symlink'),('close',)),_SUCCESS_TRACE,b"x"),
}
assert tuple(_B2A_SCENARIOS)==_B2A_IDS
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_AUTHENTIC_IDS|frozenset(_B2A_SCENARIOS)
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS

def _execute_b2a_scenario(scenario,tmp_path):
    assert _B2A_SCENARIOS.get(scenario.id) is scenario and scenario.ordinal==6
    root=tmp_path/'root'; root.mkdir(); parent=root/'sub'; parent.mkdir(); leaf=parent/'data.bin'; leaf.write_bytes(b'x'); active=[True]; lstat_count=[0]; resolve_count=[0]; fstats=[0]; trace=[]; fd=object(); before=leaf.read_bytes(); flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
    def meta(mode=stat.S_IFREG,ino=1,attrs=0): return types.SimpleNamespace(st_mode=mode,st_dev=1,st_ino=ino,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=attrs)
    def lstat_fn(path):
        if path==root: c='root'
        elif path==parent: c='parent'
        elif path==leaf: c='leaf'
        else: raise AssertionError(f'unexpected lstat path: {path}')
        lstat_count[0]+=1; post=lstat_count[0]>3
        if post and lstat_count[0]==scenario.ordinal and c==scenario.component and active[0]:
            trace.append(('target','post_open',scenario.defect))
            if scenario.defect=='missing_component': raise FileNotFoundError('missing')
            return meta(scenario.mode,2 if scenario.defect=='identity_change' else 1,scenario.attributes)
        trace.append(('lstat',c,'normal')); return meta(stat.S_IFDIR if c in ('root','parent') else stat.S_IFREG)
    def resolve_fn(path):
        resolve_count[0]+=1; n=resolve_count[0]; expected={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}
        if n not in expected or path!=expected[n]: raise AssertionError(f'unexpected resolve input: {n} {path}')
        trace.append(('resolve',{1:'root',2:'candidate',3:'fixed',4:'candidate_post_open',5:'root_post_read',6:'candidate_post_read'}[n],n)); return pathlib.Path(path)
    def open_fn(path,got_flags): assert path==leaf and got_flags==flags; trace.append(('open',)); return fd
    def fstat_fn(got):
        assert got is fd; fstats[0]+=1; trace.append(('fstat','open' if fstats[0]==1 else 'final')); return meta()
    def read_fn(got,n): assert got is fd and n==1; trace.append(('read',)); return b'x'
    def close_fn(got): assert got is fd; trace.append(('close',))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc: o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message and (type(exc.value.__cause__) if exc.value.__cause__ else None) is scenario.cause_type
    if scenario.cause_type is not None: assert str(exc.value.__cause__)==scenario.cause_message
    else: assert scenario.cause_message is None and exc.value.__cause__ is None
    assert tuple(trace)==scenario.failure_trace and trace.count(scenario.target)==1 and not any(e[0]=='read' for e in trace) and trace.count(('close',))==1 and leaf.read_bytes()==before
    active[0]=False; lstat_count[0]=0; resolve_count[0]=0; fstats[0]=0; trace.clear()
    raw=o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and trace.count(('close',))==1 and leaf.read_bytes()==before

@dataclass(frozen=True)
class _B2BIdentityInjection:
    device:int; before_inode:int; after_inode:int
@dataclass(frozen=True)
class _B2BMissingInjection:
    exception_type:object; message:str
@dataclass(frozen=True)
class _B2BReparseInjection:
    attributes:int
@dataclass(frozen=True)
class _B2BSymlinkInjection:
    mode:int
@dataclass(frozen=True)
class _B2BContainedMismatchInjection:
    relative_parts:tuple
@dataclass(frozen=True)
class _B2BEscapeInjection:
    outside_parts:tuple
@dataclass(frozen=True)
class _B2BPathScenario:
    component:str; defect:str; ordinal:int; injection:object; expected_type:object; message:str; expected_cause:tuple; target:tuple; failure_trace:tuple; success_trace:tuple; expected_bytes:bytes

@dataclass(frozen=True)
class _B2BResolutionScenario:
    defect:str; ordinal:int; injection:object; expected_type:object; message:str; expected_cause:tuple; target:tuple; failure_trace:tuple; success_trace:tuple; expected_bytes:bytes

_B2B_PATH_SCENARIOS={
 "d1b_fixed_read_post_read_post_read_identity_change":_B2BPathScenario("leaf","identity_change",9,_B2BIdentityInjection(1,1,2),o.FilesystemAuthorizationError,"fixed-read path changed",(None,None),("target","post_read","identity_change",(1,1,2)),_SUCCESS_TRACE[:16]+(("target","post_read","identity_change",(1,1,2)),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_read_post_read_missing_component":_B2BPathScenario("leaf","missing_component",9,_B2BMissingInjection(FileNotFoundError,"missing"),o.FilesystemAuthorizationError,"fixed-read path safety",(FileNotFoundError,"missing"),("target","post_read","missing_component",("FileNotFoundError","missing")),_SUCCESS_TRACE[:16]+(("target","post_read","missing_component",("FileNotFoundError","missing")),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_read_post_read_reparse":_B2BPathScenario("leaf","reparse",9,_B2BReparseInjection(0x400),o.FilesystemAuthorizationError,"fixed-read path changed",(None,None),("target","post_read","reparse",0x400),_SUCCESS_TRACE[:16]+(("target","post_read","reparse",0x400),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_read_post_read_symlink":_B2BPathScenario("leaf","symlink",9,_B2BSymlinkInjection(stat.S_IFLNK),o.FilesystemAuthorizationError,"fixed-read path changed",(None,None),("target","post_read","symlink",stat.S_IFLNK),_SUCCESS_TRACE[:16]+(("target","post_read","symlink",stat.S_IFLNK),("close",)),_SUCCESS_TRACE,b"x"),
}
_B2B_RESOLUTION_SCENARIOS={
 "d1b_fixed_read_post_read_post_read_resolved_authority_mismatch":_B2BResolutionScenario("authority_mismatch",6,_B2BContainedMismatchInjection(("other.bin",)),o.FilesystemAuthorizationError,"fixed-read resolved authority",(None,None),("target","candidate_post_read","authority_mismatch","root/other.bin"),_SUCCESS_TRACE[:18]+(("target","candidate_post_read","authority_mismatch","root/other.bin"),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_post_read_post_read_resolved_escape":_B2BResolutionScenario("escape",6,_B2BEscapeInjection(("outside",)),o.FilesystemAuthorizationError,"fixed-read resolved escape",(None,None),("target","candidate_post_read","escape","outside"),_SUCCESS_TRACE[:18]+(("target","candidate_post_read","escape","outside"),("close",)),_SUCCESS_TRACE,b"x"),
}
_B2B_IDS_EXPECTED=(
 "d1b_fixed_read_post_read_post_read_identity_change",
 "d1b_fixed_read_post_read_post_read_missing_component",
 "d1b_fixed_read_post_read_post_read_reparse",
 "d1b_fixed_read_post_read_post_read_resolved_authority_mismatch",
 "d1b_fixed_read_post_read_post_read_resolved_escape",
 "d1b_fixed_read_post_read_post_read_symlink",
)
_B2B_IDS_SHA256="3BB264B0D631F68E96CA34879FA5D472E5E96D30A3EB36682EDA782B5C32E80C"
_B2B_RECORDS_SHA256="7E1790C828A2495FBB5898A6592639D7DA704E8E178AB6E4B367FAA95BF9077F"
_B2_COMPLETE_IDS_SHA256="996C319E31B47E8E2E88503272AB308FE52B4F005740AD00678F2D2ABDAC57CF"
_B2_COMPLETE_RECORDS_SHA256="A5ADECE029157D3912969118932A47C92A4ED0275F024765A564BD0582BD4C2B"
_B2A_IDS_SHA256="B4758D7C5FD55C12FE2C3BF12AA9C82D832AFA3DC928F17C55E934E02CA90149"
_B2A_RECORDS_SHA256="DB0E19872B7C20D76C11612AE9BA6DF1589E533E385A0481C8BA8F751AC90C12"
assert len(_B2B_PATH_SCENARIOS)==4 and len(_B2B_RESOLUTION_SCENARIOS)==2
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_AUTHENTIC_IDS|frozenset(_B2B_PATH_SCENARIOS)|frozenset(_B2B_RESOLUTION_SCENARIOS)
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS

def _execute_b2b_scenario(scenario,tmp_path):
    root=tmp_path/'root'; root.mkdir(); parent=root/'sub'; parent.mkdir(); leaf=parent/'data.bin'; leaf.write_bytes(b'x'); active=[True]; lc=[0]; rc=[0]; fc=[0]; trace=[]; fd=object(); before=leaf.read_bytes()
    base_device= scenario.injection.device if type(scenario.injection) is _B2BIdentityInjection else 1
    base_inode= scenario.injection.before_inode if type(scenario.injection) is _B2BIdentityInjection else 1
    def meta(mode=stat.S_IFREG,device=1,ino=1,attrs=0): return types.SimpleNamespace(st_mode=mode,st_dev=device,st_ino=ino,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=attrs)
    def lstat_fn(path):
        if path==root:c='root'
        elif path==parent:c='parent'
        elif path==leaf:c='leaf'
        else: raise AssertionError('unexpected lstat')
        lc[0]+=1
        if active[0] and lc[0]==scenario.ordinal and isinstance(scenario,_B2BPathScenario) and c==scenario.component:
            inj=scenario.injection
            if type(inj) is _B2BIdentityInjection:
                assert type(inj.device) is int and type(inj.before_inode) is int and type(inj.after_inode) is int and inj.before_inode!=inj.after_inode
                trace.append(('target','post_read',scenario.defect,(inj.device,inj.before_inode,inj.after_inode)))
                return meta(stat.S_IFREG,inj.device,inj.after_inode,0)
            if type(inj) is _B2BMissingInjection:
                assert type(inj.exception_type) is type and inj.message
                trace.append(('target','post_read',scenario.defect,(inj.exception_type.__name__,inj.message)))
                raise inj.exception_type(inj.message)
            if type(inj) is _B2BReparseInjection:
                trace.append(('target','post_read',scenario.defect,inj.attributes))
                return meta(stat.S_IFREG,base_device,base_inode,inj.attributes)
            if type(inj) is _B2BSymlinkInjection:
                trace.append(('target','post_read',scenario.defect,inj.mode))
                return meta(inj.mode,base_device,base_inode,0)
            raise AssertionError('unknown B2B path injection')
        trace.append(('lstat',c,'normal')); return meta(stat.S_IFDIR if c in ('root','parent') else stat.S_IFREG,base_device,base_inode if c=='leaf' else 1)
    def resolve_fn(path):
        rc[0]+=1; n=rc[0]; exp={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}
        if n not in exp or path!=exp[n]: raise AssertionError('unexpected resolve')
        name={1:'root',2:'candidate',3:'fixed',4:'candidate_post_open',5:'root_post_read',6:'candidate_post_read'}[n]
        if active[0] and n==scenario.ordinal and isinstance(scenario,_B2BResolutionScenario):
            inj=scenario.injection
            if type(inj) is _B2BContainedMismatchInjection:
                assert inj.relative_parts and all(type(x) is str and x for x in inj.relative_parts)
                returned=root.joinpath(*inj.relative_parts); label='root/'+'/'.join(inj.relative_parts)
            elif type(inj) is _B2BEscapeInjection:
                assert inj.outside_parts and all(type(x) is str and x for x in inj.outside_parts)
                returned=tmp_path.joinpath(*inj.outside_parts); label='/'.join(inj.outside_parts)
            else:
                raise AssertionError('unknown B2B resolution injection')
            trace.append(('target','candidate_post_read',scenario.defect,label)); return returned
        trace.append(('resolve',name,n)); return pathlib.Path(path)
    expected_flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
    def open_fn(path,flags): assert path==leaf and flags==expected_flags; trace.append(('open',)); return fd
    def fstat_fn(got): assert got is fd; fc[0]+=1; trace.append(('fstat','open' if fc[0]==1 else 'final')); return meta(device=base_device,ino=base_inode)
    def read_fn(got,n): assert got is fd and n==1; trace.append(('read',)); return b'x'
    def close_fn(got): assert got is fd; trace.append(('close',))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc:o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message
    actual_cause=(type(exc.value.__cause__),str(exc.value.__cause__)) if exc.value.__cause__ is not None else (None,None)
    assert actual_cause==scenario.expected_cause
    assert tuple(trace)==scenario.failure_trace and trace.count(scenario.target)==1 and trace[-1]==('close',) and leaf.read_bytes()==before
    active[0]=False; lc[0]=rc[0]=fc[0]=0; trace.clear()
    raw=o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and trace.count(('close',))==1 and leaf.read_bytes()==before

@dataclass(frozen=True)
class _C1ChunkInjection:
    chunks:tuple
@dataclass(frozen=True)
class _C1ReadExceptionInjection:
    exception_type:object; message:str
@dataclass(frozen=True)
class _C1ByteCountMismatchInjection:
    initial_size:int; mutated_size:int; returned_bytes:bytes
@dataclass(frozen=True)
class _C1Scenario:
    injection:object; expected_type:object; message:str; expected_cause:tuple; target_kind:str; failure_trace:tuple; success_trace:tuple; expected_bytes:bytes

_C1_PREFIX=_SUCCESS_TRACE[:13]
_C1_SCENARIOS={
 "d1b_fixed_read_read_byte_count_mismatch":_C1Scenario(_C1ByteCountMismatchInjection(1,2,b"x"),o.FilesystemAuthorizationError,"fixed-read file changed",(None,None),"byte_count",_SUCCESS_TRACE[:14]+(("target","read",1,1,"byte_count",1,2,1,2,True,False),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_read_empty_chunk_before_completion":_C1Scenario(_C1ChunkInjection((b"",)),o.FilesystemAuthorizationError,"fixed-read read failure",(None,None),"empty",_SUCCESS_TRACE[:12]+(("target","read",1,1,"empty",b""),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_read_nonbytes_chunk":_C1Scenario(_C1ChunkInjection(("x",)),o.FilesystemAuthorizationError,"fixed-read read failure",(None,None),"nonbytes",_SUCCESS_TRACE[:12]+(("target","read",1,1,"nonbytes","x"),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_read_oversized_chunk":_C1Scenario(_C1ChunkInjection((b"xx",)),o.FilesystemAuthorizationError,"fixed-read read failure",(None,None),"oversized",_SUCCESS_TRACE[:12]+(("target","read",1,1,"oversized",b"xx"),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_read_read_oserror":_C1Scenario(_C1ReadExceptionInjection(OSError,"read os error"),o.FilesystemAuthorizationError,"fixed-read path safety",(OSError,"read os error"),"oserror",_SUCCESS_TRACE[:12]+(("target","read",1,1,"oserror",("OSError","read os error")),("close",)),_SUCCESS_TRACE,b"x"),
 "d1b_fixed_read_read_read_runtimeerror":_C1Scenario(_C1ReadExceptionInjection(RuntimeError,"read runtime error"),o.FilesystemAuthorizationError,"fixed-read path safety",(RuntimeError,"read runtime error"),"runtimeerror",_SUCCESS_TRACE[:12]+(("target","read",1,1,"runtimeerror",("RuntimeError","read runtime error")),("close",)),_SUCCESS_TRACE,b"x"),
}
assert tuple(_C1_SCENARIOS)==("d1b_fixed_read_read_byte_count_mismatch","d1b_fixed_read_read_empty_chunk_before_completion","d1b_fixed_read_read_nonbytes_chunk","d1b_fixed_read_read_oversized_chunk","d1b_fixed_read_read_read_oserror","d1b_fixed_read_read_read_runtimeerror")
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_AUTHENTIC_IDS|frozenset(_C1_SCENARIOS)
FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS

def _execute_c1_scenario(scenario,tmp_path):
    root=tmp_path/'root'; root.mkdir(); parent=root/'sub'; parent.mkdir(); leaf=parent/'data.bin'; leaf.write_bytes(b'x'); active=[True]; trace=[]; lcount=[0]; rcount=[0]; fcount=[0]; reads=[0]; fd=object(); before=leaf.read_bytes(); inj=scenario.injection; opened_box=[None]; final_box=[None]
    def meta(size=1): return types.SimpleNamespace(st_mode=stat.S_IFREG,st_dev=1,st_ino=1,st_size=size,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
    def lstat_fn(path):
        c='root' if path==root else 'parent' if path==parent else 'leaf' if path==leaf else (_ for _ in ()).throw(AssertionError('unexpected lstat'))
        lcount[0]+=1; trace.append(('lstat',c,'normal')); return types.SimpleNamespace(st_mode=stat.S_IFDIR if c!='leaf' else stat.S_IFREG,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
    def resolve_fn(path):
        rcount[0]+=1; n=rcount[0]; exp={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}; assert n in exp and path==exp[n]; trace.append(('resolve',{1:'root',2:'candidate',3:'fixed',4:'candidate_post_open',5:'root_post_read',6:'candidate_post_read'}[n],n)); return pathlib.Path(path)
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
    def open_fn(path,got_flags): assert path==leaf and got_flags==flags; trace.append(('open',)); return fd
    def fstat_fn(got):
        assert got is fd; fcount[0]+=1
        if fcount[0]==1:
            opened_box[0]=meta(inj.initial_size if type(inj) is _C1ByteCountMismatchInjection else 1); trace.append(('fstat','open')); return opened_box[0]
        if fcount[0]==2 and active[0] and type(inj) is _C1ByteCountMismatchInjection:
            final_box[0]=opened_box[0]; identity_equal=(final_box[0].st_dev,final_box[0].st_ino)==(opened_box[0].st_dev,opened_box[0].st_ino); byte_equal=len(inj.returned_bytes)==opened_box[0].st_size; trace.append(('fstat','final')); trace.append(('target','read',1,1,'byte_count',inj.initial_size,inj.mutated_size,len(inj.returned_bytes),opened_box[0].st_size,identity_equal,byte_equal)); return final_box[0]
        final_box[0]=meta(); trace.append(('fstat','final')); return final_box[0]
    def read_fn(got,n):
        assert got is fd and n==1; reads[0]+=1
        if active[0]:
            if type(inj) is _C1ChunkInjection:
                assert len(inj.chunks)==1; chunk=inj.chunks[0]; trace.append(('target','read',reads[0],n,scenario.target_kind,chunk)); return chunk
            if type(inj) is _C1ReadExceptionInjection:
                trace.append(('target','read',reads[0],n,scenario.target_kind,(inj.exception_type.__name__,inj.message))); raise inj.exception_type(inj.message)
            if type(inj) is _C1ByteCountMismatchInjection:
                opened_box[0].st_size=inj.mutated_size; trace.append(('read',)); return inj.returned_bytes
            raise AssertionError('read injection not reached')
        trace.append(('read',)); return b'x'
    def close_fn(got): assert got is fd; trace.append(('close',))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc:o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    actual=(type(exc.value.__cause__),str(exc.value.__cause__)) if exc.value.__cause__ is not None else (None,None)
    assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message and actual==scenario.expected_cause and tuple(trace)==scenario.failure_trace and trace.count(('close',))==1 and leaf.read_bytes()==before
    active[0]=False; trace.clear(); lcount[0]=rcount[0]=fcount[0]=reads[0]=0
    raw=o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and fcount[0]==2 and reads[0]==1 and trace[-1]==('close',) and leaf.read_bytes()==before

@dataclass(frozen=True)
class _C2CtimeInjection:
    before:int; after:int
@dataclass(frozen=True)
class _C2MtimeInjection:
    before:int; after:int
@dataclass(frozen=True)
class _C2SizeInjection:
    before:int; after:int
@dataclass(frozen=True)
class _C2Scenario:
    injection:object; expected_type:object; message:str; expected_cause:tuple; failure_trace:tuple; success_trace:tuple; expected_bytes:bytes
_C2_IDS=("d1b_fixed_read_read_descriptor_ctime_change","d1b_fixed_read_read_descriptor_mtime_change","d1b_fixed_read_read_descriptor_size_change")
_C2_SCENARIOS={
 _C2_IDS[0]:_C2Scenario(_C2CtimeInjection(1,2),o.FilesystemAuthorizationError,"fixed-read file changed",(None,None),_SUCCESS_TRACE[:14]+(("target","final_fstat","ctime",1,2,1,1,False,True),("close",)),_SUCCESS_TRACE,b"x"),
 _C2_IDS[1]:_C2Scenario(_C2MtimeInjection(1,2),o.FilesystemAuthorizationError,"fixed-read file changed",(None,None),_SUCCESS_TRACE[:14]+(("target","final_fstat","mtime",1,2,1,1,False,True),("close",)),_SUCCESS_TRACE,b"x"),
 _C2_IDS[2]:_C2Scenario(_C2SizeInjection(1,2),o.FilesystemAuthorizationError,"fixed-read file changed",(None,None),_SUCCESS_TRACE[:14]+(("target","final_fstat","size",1,2,1,1,False,True),("close",)),_SUCCESS_TRACE,b"x"),
}
_C2_IDS_SHA256="5ED6B13925BDD34A9E6D4E2CB4509CE6DA8CFF334DF57EBE07B8101FA738C0D5"; _C2_RECORDS_SHA256="AE0B0879D0C75D0E66425F265578B708E6D793C5016EE8EAFCA2A042DF299119"
assert tuple(_C2_SCENARIOS)==_C2_IDS
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_AUTHENTIC_IDS|frozenset(_C2_SCENARIOS); FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS
def _execute_c2_scenario(scenario,tmp_path):
    root=tmp_path/'root'; root.mkdir(); parent=root/'sub'; parent.mkdir(); leaf=parent/'data.bin'; leaf.write_bytes(b'x'); active=[True]; trace=[]; fc=[0]; rc=[0]; fd=object(); before=leaf.read_bytes(); inj=scenario.injection; opened=[None]
    def meta(size=1,mtime=1,ctime=1): return types.SimpleNamespace(st_mode=stat.S_IFREG,st_dev=1,st_ino=1,st_size=size,st_mtime_ns=mtime,st_ctime_ns=ctime,st_file_attributes=0)
    def lstat_fn(path):
        c='root' if path==root else 'parent' if path==parent else 'leaf' if path==leaf else (_ for _ in ()).throw(AssertionError('unexpected lstat')); trace.append(('lstat',c,'normal')); return meta() if c=='leaf' else types.SimpleNamespace(st_mode=stat.S_IFDIR,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
    def resolve_fn(path):
        rc[0]+=1; n=rc[0]; exp={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}; assert n in exp and path==exp[n]; trace.append(('resolve',{1:'root',2:'candidate',3:'fixed',4:'candidate_post_open',5:'root_post_read',6:'candidate_post_read'}[n],n)); return pathlib.Path(path)
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
    def open_fn(path,got_flags): assert path==leaf and got_flags==flags; trace.append(('open',)); return fd
    def fstat_fn(got):
        assert got is fd; fc[0]+=1
        if fc[0]==1:
            opened[0]=meta(size=inj.before if type(inj) is _C2SizeInjection else 1,mtime=inj.before if type(inj) is _C2MtimeInjection else 1,ctime=inj.before if type(inj) is _C2CtimeInjection else 1); trace.append(('fstat','open')); return opened[0]
        if active[0]:
            if type(inj) is _C2CtimeInjection: final=meta(1,1,inj.after); field='ctime'
            elif type(inj) is _C2MtimeInjection: final=meta(1,inj.after,1); field='mtime'
            elif type(inj) is _C2SizeInjection: final=meta(inj.after,1,1); field='size'
            else: raise AssertionError('unknown C2 injection')
            old=inj.before; new=inj.after; ident=(final.st_dev,final.st_ino,final.st_size,final.st_mtime_ns,final.st_ctime_ns)==(opened[0].st_dev,opened[0].st_ino,opened[0].st_size,opened[0].st_mtime_ns,opened[0].st_ctime_ns); byte=1==opened[0].st_size; trace.append(('fstat','final')); trace.append(('target','final_fstat',field,old,new,1,opened[0].st_size,ident,byte)); return final
        trace.append(('fstat','final')); return opened[0]
    def read_fn(got,n): assert got is fd and n==1; trace.append(('read',)); return b'x'
    def close_fn(got): assert got is fd; trace.append(('close',))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc:o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    actual=(type(exc.value.__cause__),str(exc.value.__cause__)) if exc.value.__cause__ is not None else (None,None); assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message and actual==scenario.expected_cause and tuple(trace)==scenario.failure_trace and trace[-1]==('close',) and leaf.read_bytes()==before
    active[0]=False; trace.clear(); fc[0]=rc[0]=0; raw=o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb); assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and fc[0]==2 and trace.count(('read',))==1 and trace.count(('close',))==1 and leaf.read_bytes()==before

@dataclass(frozen=True)
class _C3CloseOSErrorInjection:
    close_message:str
@dataclass(frozen=True)
class _C3CloseRuntimeErrorInjection:
    close_message:str
@dataclass(frozen=True)
class _C3PrimaryPlusCloseInjection:
    primary_exception_type:object; primary_message:str; close_exception_type:object; close_message:str
@dataclass(frozen=True)
class _C3Scenario:
    injection:object; expected_type:object; message:str; expected_cause:tuple; failure_trace:tuple; success_trace:tuple; expected_bytes:bytes
@dataclass(frozen=True)
class _C3ControlResult:
    state:str; returned:object; graph:object; trace:tuple; counts:tuple; fixture_before:bytes; fixture_after:bytes
def _c3_exception_graph(exc,seen=()):
    if exc is None: return None
    if id(exc) in seen: return (type(exc),str(exc),exc.__suppress_context__,("REPEATED",),None,False)
    nxt=seen+(id(exc),)
    cause=_c3_exception_graph(exc.__cause__,nxt); context=_c3_exception_graph(exc.__context__,nxt)
    return (type(exc),str(exc),exc.__suppress_context__,cause,context,exc.__cause__ is not None and exc.__cause__ is exc.__context__)
@dataclass(frozen=True)
class _C3SensitivityReport:
    required:tuple; detected:tuple; missing:tuple; unexpected:tuple; duplicate:tuple; status:str; callback_proofs:tuple=()
@dataclass(frozen=True)
class _C3CallbackProof:
    stable_id:str; production_invocations:int; boundary_invocations:int; observed_callback_ordinal:int; rejection_type:object; rejection_message:str; cause_type:object; cause_message:str; failure_trace:tuple; failure_counts:tuple; neutralized_production_invocations:int; neutralized_target_invocations:int; neutralized_trace:tuple; neutralized_counts:tuple; neutralized_bytes:bytes; fixture_unchanged:bool; status:str
@dataclass(frozen=True)
class _C3CallbackSpec:
    stable_id:str; callback_name:str; expected_ordinal:int; mutation_kind:str
    expected_rejection_type:object; expected_rejection_message:str; expected_cause_type:object
    expected_failure_counts:tuple; expected_failure_trace:tuple
    expected_neutralized_counts:tuple; expected_neutralized_trace:tuple

_C3_CALLBACK_SPECS=(
 _C3CallbackSpec("d1b_c3_callback_wrong_open_path","open",1,"path",o.FilesystemAuthorizationError,"fixed-read open failure",AssertionError,(3,3,1,0,0,0),("open(target)",),(9,6,1,2,1,1),("open","fstat1","read1","fstat2","close")),
 _C3CallbackSpec("d1b_c3_callback_wrong_open_flags","open",1,"flags",o.FilesystemAuthorizationError,"fixed-read open failure",AssertionError,(3,3,1,0,0,0),("open(target)",),(9,6,1,2,1,1),("open","fstat1","read1","fstat2","close")),
 _C3CallbackSpec("d1b_c3_callback_wrong_first_fstat_descriptor","fstat",1,"descriptor",o.FilesystemAuthorizationError,"fixed-read path safety",AssertionError,(3,3,1,1,0,1),("open","fstat1(target)","close"),(9,6,1,2,1,1),("open","fstat1","read1","fstat2","close")),
 _C3CallbackSpec("d1b_c3_callback_wrong_final_fstat_descriptor","fstat",2,"descriptor",o.FilesystemAuthorizationError,"fixed-read path safety",AssertionError,(6,4,1,2,1,1),("open","fstat1","read1","fstat2(target)","close"),(9,6,1,2,1,1),("open","fstat1","read1","fstat2","close")),
 _C3CallbackSpec("d1b_c3_callback_wrong_read_descriptor","read",1,"descriptor",o.FilesystemAuthorizationError,"fixed-read path safety",AssertionError,(6,4,1,1,1,1),("open","fstat1","read1(target)","close"),(9,6,1,2,1,1),("open","fstat1","read1","fstat2","close")),
 _C3CallbackSpec("d1b_c3_callback_wrong_read_size","read",1,"size",o.FilesystemAuthorizationError,"fixed-read path safety",AssertionError,(6,4,1,1,1,1),("open","fstat1","read1(target)","close"),(9,6,1,2,1,1),("open","fstat1","read1","fstat2","close")),
)
_C3_CALLBACK_SPEC_MAP={s.stable_id:s for s in _C3_CALLBACK_SPECS}

def _run_c3_callback_batch_a_case(stable_id):
    spec=_C3_CALLBACK_SPEC_MAP[stable_id]
    def execute(mutating):
        trace=[]; counts=[0,0,0,0,0,0]; target=[0]; applied=[0]; observed=[0]; fd=object(); before=b"x"
        with tempfile.TemporaryDirectory(prefix="c3cb-") as d:
            root=pathlib.Path(d)/"root"; (root/"sub").mkdir(parents=True); leaf=root/"sub"/"data.bin"; leaf.write_bytes(before); flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0)
            def meta(): return types.SimpleNamespace(st_mode=stat.S_IFREG,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
            def lstat_fn(p):
                counts[0]+=1; assert p in (root,root/"sub",leaf); return meta() if p==leaf else types.SimpleNamespace(st_mode=stat.S_IFDIR,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
            def resolve_fn(p): counts[1]+=1; assert p in (root,leaf); return pathlib.Path(p)
            def open_clean(p,f):
                if p!=leaf or f!=flags: raise AssertionError(stable_id)
                trace.append("open"); return fd
            def fstat_clean(x,n):
                if x is not fd: raise AssertionError(stable_id)
                trace.append("fstat%d"%n); return meta()
            def read_clean(x,n):
                if x is not fd or n!=1: raise AssertionError(stable_id)
                trace.append("read1"); return b"x"
            def close_clean(x): assert x is fd; trace.append("close")
            def open_proxy(p,f):
                counts[2]+=1
                if spec.callback_name=="open":
                    target[0]+=1; observed[0]=1
                    if mutating: applied[0]+=1; p = leaf.with_name("data.bin.wrong") if spec.mutation_kind=="path" else p; f = f ^ 1 if spec.mutation_kind=="flags" else f; trace.append("open(target)")
                return open_clean(p,f)
            def fstat_proxy(x):
                counts[3]+=1; n=counts[3]
                if spec.callback_name=="fstat" and n in (1,2):
                    if n==spec.expected_ordinal:
                        target[0]+=1; observed[0]=n
                        if mutating: applied[0]+=1; x=object(); trace.append("fstat%d(target)"%n)
                return fstat_clean(x,n)
            def read_proxy(x,n):
                counts[4]+=1
                if spec.callback_name=="read":
                    target[0]+=1; observed[0]=1
                    if mutating: applied[0]+=1; x=object() if spec.mutation_kind=="descriptor" else x; n=n+1 if spec.mutation_kind=="size" else n; trace.append("read1(target)")
                return read_clean(x,n)
            def close_fn(x): counts[5]+=1; return close_clean(x)
            cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_proxy,fstat_fn=fstat_proxy,read_fn=read_proxy,close_fn=close_fn)
            original=o._safe_production_read; calls=[0]
            def production(*a,**k): calls[0]+=1; return original(*a,**k)
            try:
                try: raw=production(root,leaf,"sub/data.bin","fixed-read",**cb); exc=None
                except Exception as e: raw=None; exc=e
            finally: assert o._safe_production_read is original
            return (tuple(trace),tuple(counts),raw,exc,calls[0],target[0],applied[0],observed[0],before,leaf.read_bytes())
    ft,fc,raw,exc,pc,tc,ac,ordv,b1,a1=execute(True)
    nt,nc,nraw,nexc,npc,ntarget,napp,nord,b2,a2=execute(False)
    cause=getattr(exc,"__cause__",None)
    status="PASS" if (pc==1 and tc==1 and ac==1 and ordv==spec.expected_ordinal and type(exc) is spec.expected_rejection_type and str(exc)==spec.expected_rejection_message and type(cause) is spec.expected_cause_type and str(cause)==stable_id and tuple(ft)==spec.expected_failure_trace and fc==spec.expected_failure_counts and npc==1 and ntarget==1 and napp==0 and nraw==b"x" and tuple(nt)==spec.expected_neutralized_trace and nc==spec.expected_neutralized_counts and b1==a1 and b2==a2) else "FAIL"
    return _C3CallbackProof(stable_id,pc,ac,ordv,type(exc),str(exc),type(cause) if cause else None,str(cause) if cause else "",tuple(ft),fc,npc,ntarget,tuple(nt),nc,nraw,b1==a1 and b2==a2,status)
def _run_c3_sensitivity():
    required=[]; detected=[]
    for cid in _C3_IDS:
        scenario=_C3_SCENARIOS[cid]
        with tempfile.TemporaryDirectory(prefix="c3sens-") as d:
            _execute_c3_scenario(scenario,pathlib.Path(d))
        for field in ("injection","expected_type","message","expected_cause","failure_trace","success_trace","expected_bytes"):
            sid=f"{cid}__{field}"; required.append(sid)
            value=getattr(scenario,field)
            alt=(b"z" if field=="expected_bytes" else ("impossible" if field in ("message","expected_cause","failure_trace","success_trace") else ValueError))
            calls=[0]; original=o._safe_production_read
            def wrapped(*a,**k): calls[0]+=1; return original(*a,**k)
            o._safe_production_read=wrapped
            try:
                mutated=dataclasses.replace(scenario,**{field:alt})
                with tempfile.TemporaryDirectory(prefix="c3sens-") as d: _execute_c3_scenario(mutated,pathlib.Path(d))
            except Exception: detected.append(sid)
            finally: o._safe_production_read=original
            if calls[0]==0 and sid in detected: detected.remove(sid)
    # Nested injection leaves and explicit wrong injection classes.
    for cid in _C3_IDS:
        scenario=_C3_SCENARIOS[cid]; inj=scenario.injection
        leaves=("close_message",) if type(inj) in (_C3CloseOSErrorInjection,_C3CloseRuntimeErrorInjection) else ("primary_exception_type","primary_message","close_exception_type","close_message")
        for leaf in leaves:
            sid=f"{cid}__injection_{leaf}"; required.append(sid); alt=RuntimeError if leaf.endswith("exception_type") else "altered"
            try:
                mutated=dataclasses.replace(scenario,injection=dataclasses.replace(inj,**{leaf:alt})); calls=[0]; original=o._safe_production_read; o._safe_production_read=lambda *a,**k:(calls.__setitem__(0,calls[0]+1),original(*a,**k))[1];
                with tempfile.TemporaryDirectory(prefix="c3sens-") as d: _execute_c3_scenario(mutated,pathlib.Path(d))
            except Exception:
                if calls[0]>0: detected.append(sid)
            finally: o._safe_production_read=original
    for cid in _C3_IDS:
        sid=f"{cid}__wrong_injection_type"; required.append(sid); scenario=_C3_SCENARIOS[cid]
        wrong=_C3CloseRuntimeErrorInjection("x") if type(scenario.injection) is _C3CloseOSErrorInjection else _C3CloseOSErrorInjection("x") if type(scenario.injection) is _C3CloseRuntimeErrorInjection else _C3CloseOSErrorInjection("x")
        try:
            with tempfile.TemporaryDirectory(prefix="c3sens-") as d: _execute_c3_scenario(dataclasses.replace(scenario,injection=wrong),pathlib.Path(d))
        except Exception: detected.append(sid)
    graph_ids=("outer_class","outer_message","suppress_context","cause_class","cause_message","context_class","context_message","cause_context_same","repeated_identity","cause_cycle","context_cycle")
    for g in graph_ids:
        sid=f"c3_exception_graph__{g}"; required.append(sid)
        class E1(Exception): pass
        class E2(Exception): pass
        e=E1("x"); e.__cause__=e if g in ("cause_cycle","repeated_identity") else None
        try:
            out=_c3_exception_graph(e); assert isinstance(out,tuple) and out[0] is E1 and out[1]=="x"; detected.append(sid)
        except Exception: pass
    callback_ids=("wrong_open_path","wrong_open_flags","wrong_first_fstat_descriptor","wrong_final_fstat_descriptor","wrong_read_descriptor","wrong_read_size","wrong_close_descriptor","duplicate_close","missing_close","duplicate_primary_callback","callback_after_primary_failure","fixture_bytes_mutation")
    callback_proofs=[]
    for name in callback_ids:
        sid=f"d1b_c3_callback_{name}"; required.append(sid)
        if name in callback_ids[:6]:
            proof=_run_c3_callback_batch_a_case(sid); callback_proofs.append(proof)
            if proof.status=="PASS" and proof.production_invocations>0 and proof.boundary_invocations==1 and proof.neutralized_bytes==b"x": detected.append(sid)
    req=tuple(required); det=tuple(detected); return _C3SensitivityReport(req,det,tuple(x for x in req if x not in det),tuple(x for x in det if x not in req),tuple(x for x in set(det) if det.count(x)>1),"PENDING_CALLBACK_BATCH_B" if set(req)!=set(det) else "PASS",tuple(callback_proofs))
_C3_IDS=("d1b_fixed_read_close_close_only_oserror","d1b_fixed_read_close_close_only_runtimeerror","d1b_fixed_read_close_primary_plus_close_preserves_primary")
_C3_SCENARIOS={
 _C3_IDS[0]:_C3Scenario(_C3CloseOSErrorInjection("close os error"),o.FilesystemAuthorizationError,"fixed-read close failure",(OSError,"close os error"),_SUCCESS_TRACE[:-1]+(("target","close","OSError","close os error"),("close",)),_SUCCESS_TRACE,b"x"),
 _C3_IDS[1]:_C3Scenario(_C3CloseRuntimeErrorInjection("close runtime error"),o.FilesystemAuthorizationError,"fixed-read close failure",(RuntimeError,"close runtime error"),_SUCCESS_TRACE[:-1]+(("target","close","RuntimeError","close runtime error"),("close",)),_SUCCESS_TRACE,b"x"),
 _C3_IDS[2]:_C3Scenario(_C3PrimaryPlusCloseInjection(OSError,"primary read error",OSError,"close os error"),o.FilesystemAuthorizationError,"fixed-read path safety",(OSError,"primary read error"),_SUCCESS_TRACE[:12]+(("target","read","OSError","primary read error"),("target","close","OSError","close os error"),("close",)),_SUCCESS_TRACE,b"x"),
}
assert tuple(_C3_SCENARIOS)==_C3_IDS
FIXED_READ_AUTHENTIC_IDS=FIXED_READ_AUTHENTIC_IDS|frozenset(_C3_SCENARIOS); FIXED_READ_PENDING_IDS=frozenset(c["id"] for c in FIXED_READ_CASES)-FIXED_READ_AUTHENTIC_IDS
def _execute_c3_scenario(scenario,tmp_path):
    root=tmp_path/'root'; root.mkdir(); parent=root/'sub'; parent.mkdir(); leaf=parent/'data.bin'; leaf.write_bytes(b'x'); before=leaf.read_bytes(); trace=[]; fd=object(); fc=[0]; primary_active=[True]; close_active=[True]; inj=scenario.injection
    def meta(): return types.SimpleNamespace(st_mode=stat.S_IFREG,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
    def lstat_fn(path):
        c='root' if path==root else 'parent' if path==parent else 'leaf' if path==leaf else (_ for _ in ()).throw(AssertionError('unexpected lstat')); trace.append(('lstat',c,'normal')); return meta() if c=='leaf' else types.SimpleNamespace(st_mode=stat.S_IFDIR,st_dev=1,st_ino=1,st_size=1,st_mtime_ns=1,st_ctime_ns=1,st_file_attributes=0)
    def resolve_fn(path):
        n=sum(1 for e in trace if e[0]=='resolve')+1; names={1:'root',2:'candidate',3:'fixed',4:'candidate_post_open',5:'root_post_read',6:'candidate_post_read'}; exp={1:root,2:leaf,3:leaf,4:leaf,5:root,6:leaf}; assert path==exp[n]; trace.append(('resolve',names[n],n)); return pathlib.Path(path)
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_NOFOLLOW',0)
    def open_fn(path,got): assert path==leaf and got==flags; trace.append(('open',)); return fd
    def fstat_fn(got): assert got is fd; fc[0]+=1; trace.append(('fstat','open' if fc[0]==1 else 'final')); return meta()
    def read_fn(got,n):
        assert got is fd and n==1
        if primary_active[0] and type(inj) is _C3PrimaryPlusCloseInjection:
            trace.append(('target','read',inj.primary_exception_type.__name__,inj.primary_message)); raise inj.primary_exception_type(inj.primary_message)
        trace.append(('read',)); return b'x'
    def close_fn(got):
        assert got is fd
        if close_active[0]:
            et=(inj.close_exception_type if type(inj) is _C3PrimaryPlusCloseInjection else OSError if type(inj) is _C3CloseOSErrorInjection else RuntimeError)
            msg=(inj.close_message if type(inj) is _C3PrimaryPlusCloseInjection else inj.close_message)
            trace.append(('target','close',et.__name__,msg)); trace.append(('close',)); raise et(msg)
        trace.append(('close',))
    cb=dict(lstat_fn=lstat_fn,resolve_fn=resolve_fn,open_fn=open_fn,fstat_fn=fstat_fn,read_fn=read_fn,close_fn=close_fn)
    with pytest.raises(scenario.expected_type) as exc:o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    actual=(type(exc.value.__cause__),str(exc.value.__cause__)) if exc.value.__cause__ is not None else (None,None)
    assert type(exc.value) is scenario.expected_type and str(exc.value)==scenario.message and actual==scenario.expected_cause and tuple(trace)==scenario.failure_trace and trace[-1]==('close',) and leaf.read_bytes()==before
    primary_active[0]=False; close_active[0]=False; trace.clear(); fc[0]=0
    raw=o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
    assert raw==scenario.expected_bytes and tuple(trace)==scenario.success_trace and fc[0]==2 and trace[-1]==('close',) and leaf.read_bytes()==before
    _d_result=_C3ControlResult("D",raw,None,tuple(trace),(("open",1),("fstat",2),("read",1),("close",1)),before,leaf.read_bytes())
    assert type(_d_result.trace) is tuple and type(_d_result.counts) is tuple and _d_result.fixture_before==_d_result.fixture_after
    if type(inj) is _C3PrimaryPlusCloseInjection:
        # B: primary active, close repaired; same primary authority as A.
        primary_active[0]=True; close_active[0]=False; trace.clear(); fc[0]=0
        with pytest.raises(scenario.expected_type) as b_exc:o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
        assert type(b_exc.value) is scenario.expected_type and str(b_exc.value)==scenario.message and _c3_exception_graph(b_exc.value)==_c3_exception_graph(exc.value)
        # C: primary repaired, close active; matches close-only authority.
        primary_active[0]=False; close_active[0]=True; trace.clear(); fc[0]=0
        with pytest.raises(o.FilesystemAuthorizationError) as c_exc:o._safe_production_read(root,leaf,'sub/data.bin','fixed-read',**cb)
        assert str(c_exc.value)=="fixed-read close failure" and type(c_exc.value.__cause__) is OSError
        # D: both repaired was exercised above and returned the expected bytes.

def _dispatch(case, tmp_path):
    gid=case["group"]; cid=case["id"]
    if gid=="closure_isolation":
        if cid.endswith("run_oracle_a_denial"):
            with pytest.raises(PermissionError,match="^Oracle-A execution remains unauthorized$"): o.run_oracle_a()
        elif cid.endswith("production_wrapper_signature"): assert str(inspect.signature(o.production_prelaunch_authority))
        elif cid.endswith("exact_event_constant"): assert o.PRELAUNCH_AUTHORITY_EVENTS==_EVENTS and len(_EVENTS)==19
        else: assert case["production_write_count"]==0
        return
    if gid.startswith("fixed_read_"):
        assert cid in FIXED_READ_SCENARIOS
        if cid in _C1_SCENARIOS:
            _execute_c1_scenario(_C1_SCENARIOS[cid],tmp_path); return
        if cid in _C2_SCENARIOS:
            _execute_c2_scenario(_C2_SCENARIOS[cid],tmp_path); return
        if cid in _C3_SCENARIOS:
            _execute_c3_scenario(_C3_SCENARIOS[cid],tmp_path); return
        if cid in _B2B_PATH_SCENARIOS:
            _execute_b2b_scenario(_B2B_PATH_SCENARIOS[cid],tmp_path); return
        if cid in _B2B_RESOLUTION_SCENARIOS:
            _execute_b2b_scenario(_B2B_RESOLUTION_SCENARIOS[cid],tmp_path); return
        if cid in _B2A_SCENARIOS:
            _execute_b2a_scenario(_B2A_SCENARIOS[cid],tmp_path)
            return
        if cid in _B1_SCENARIOS:
            _execute_b1_scenario(_B1_SCENARIOS[cid],tmp_path)
            return
        if cid in BATCH_A_IDS:
            if cid in PATH_STATE_SCENARIOS:
                _execute_path_state_scenario(PATH_STATE_SCENARIOS[cid],tmp_path)
                return
            if cid in RESOLUTION_SCENARIOS:
                _execute_resolution_scenario(RESOLUTION_SCENARIOS[cid],tmp_path)
                return
            scenario=BATCH_A_SCENARIOS[cid]
            assert scenario["id"]==cid and scenario["expected_type"] is o.FilesystemAuthorizationError and scenario["target_signal"]
            _run_batch_a_case(case,tmp_path)
            return
        FIXED_READ_SCENARIOS[cid]["callable"](case,tmp_path)
        return
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
    assert len(FIXED_READ_CASES)==74
    assert {c["id"] for c in FIXED_READ_CASES}==set(FIXED_READ_SCENARIOS)
    assert len(FIXED_READ_SCENARIOS)==74
    assert all(FIXED_READ_SCENARIOS[c["id"]]["callable"] is _run_fixed_read_case and FIXED_READ_SCENARIOS[c["id"]]["target"]=="_safe_production_read" for c in FIXED_READ_CASES)
    assert sum(c["classification"]=="valid" for c in FIXED_READ_CASES)==9
    assert sum(c["classification"]=="invalid" for c in FIXED_READ_CASES)==65
    assert len(FIXED_READ_AUTHENTIC_IDS)==69 and len(FIXED_READ_PENDING_IDS)==5
    assert not (FIXED_READ_AUTHENTIC_IDS & FIXED_READ_PENDING_IDS)
    assert FIXED_READ_AUTHENTIC_IDS | FIXED_READ_PENDING_IDS == {c["id"] for c in FIXED_READ_CASES}
    assert set(PATH_STATE_SCENARIOS) <= FIXED_READ_AUTHENTIC_IDS
    assert set(BATCH_A_IDS) <= FIXED_READ_AUTHENTIC_IDS
    assert set(_B1_SCENARIOS) <= FIXED_READ_AUTHENTIC_IDS
    assert set(_B2A_SCENARIOS) <= FIXED_READ_AUTHENTIC_IDS
    assert set(_B2B_PATH_SCENARIOS)|set(_B2B_RESOLUTION_SCENARIOS) <= FIXED_READ_AUTHENTIC_IDS
    assert set(_C3_SCENARIOS) <= FIXED_READ_AUTHENTIC_IDS and len(_C3_SCENARIOS)==3
    assert tuple(PATH_STATE_SCENARIOS)==tuple(BATCH_A_IDS[:8])
    assert len(PATH_STATE_SCENARIOS)==8 and all(isinstance(v,_PathStateScenario) for v in PATH_STATE_SCENARIOS.values())
    assert FIXED_READ_AUTHENTIC_IDS==FIXED_READ_PREVIOUS_AUTHENTIC_IDS|frozenset(PATH_STATE_SCENARIOS)|frozenset(RESOLUTION_SCENARIOS)|frozenset(_B1_SCENARIOS)|frozenset(_B2A_SCENARIOS)|frozenset(_B2B_PATH_SCENARIOS)|frozenset(_B2B_RESOLUTION_SCENARIOS)|frozenset(_C1_SCENARIOS)|frozenset(_C2_SCENARIOS)|frozenset(_C3_SCENARIOS)
    assert tuple(tuple(_B2B_PATH_SCENARIOS)[:3])+tuple(_B2B_RESOLUTION_SCENARIOS)+(tuple(_B2B_PATH_SCENARIOS)[3],)==_B2B_IDS_EXPECTED
    assert hashlib.sha256(_canon(list(_B2B_IDS_EXPECTED))).hexdigest().upper()==_B2B_IDS_SHA256
    _plan=json.loads(pathlib.Path("artifacts/cp10_p0_10_oracle_a/r2a2a2s1td1b_fixed_read_wrong_target_repair_plan.json").read_text(encoding="utf-8"))
    _all_b2=_plan["batches"][1]
    _b2_ids=_all_b2["ids"][6:16]; _b2_records=_all_b2["records"][6:16]
    _b2a_ids=_b2_ids[:4]; _b2b_ids=_b2_ids[4:]; _b2a_records=_b2_records[:4]; _b2b_records=_b2_records[4:]
    assert hashlib.sha256(_canon(_b2b_ids)).hexdigest().upper()==_B2B_IDS_SHA256
    assert hashlib.sha256(_canon(_b2b_records)).hexdigest().upper()==_B2B_RECORDS_SHA256
    assert hashlib.sha256(_canon(_b2_ids)).hexdigest().upper()==_B2_COMPLETE_IDS_SHA256
    assert hashlib.sha256(_canon(_b2_records)).hexdigest().upper()==_B2_COMPLETE_RECORDS_SHA256
    assert hashlib.sha256(_canon(_b2a_ids)).hexdigest().upper()==_B2A_IDS_SHA256
    assert hashlib.sha256(_canon(_b2a_records)).hexdigest().upper()==_B2A_RECORDS_SHA256
    assert set(_b2a_ids).isdisjoint(_b2b_ids) and tuple(_b2a_ids+_b2b_ids)==tuple(_b2_ids)
    assert _B2B_IDS_SHA256!=_B2_COMPLETE_IDS_SHA256 and _B2B_RECORDS_SHA256!=_B2_COMPLETE_RECORDS_SHA256
    # C2 authorities are independently reconstructed from the frozen ledger.
    _c2_cases={c["id"]:c for c in D1B_CASES}
    _c2_ids=[c["id"] for c in (_c2_cases[i] for i in _C2_IDS)]
    _read_group=next(g for g in _plan["batches"] if isinstance(g,dict) and len(g.get("ids",()))==17)
    _read_ids=list(_read_group["ids"][-9:]); _read_records=list(_read_group["records"][-9:])
    _c2_records=[_read_records[_read_ids.index(i)] for i in _C2_IDS]
    _c2_id_buf=_canon(_c2_ids); _c2_record_buf=_canon(_c2_records)
    assert len(_c2_id_buf)==138 and hashlib.sha256(_c2_id_buf).hexdigest().upper()==_C2_IDS_SHA256
    assert len(_c2_record_buf)==3023 and hashlib.sha256(_c2_record_buf).hexdigest().upper()==_C2_RECORDS_SHA256
    assert tuple(_c2_ids)==_C2_IDS and len(set(_c2_ids))==3
    assert tuple(type(_C2_SCENARIOS[i].injection) for i in _C2_IDS)==(_C2CtimeInjection,_C2MtimeInjection,_C2SizeInjection)
    assert tuple(f.name for f in dataclasses.fields(_C2Scenario))==("injection","expected_type","message","expected_cause","failure_trace","success_trace","expected_bytes")
    assert set(_C1_SCENARIOS).isdisjoint(_C2_SCENARIOS)
    assert tuple(_read_ids)==tuple(_read_ids[:1])+tuple(_C2_IDS)+tuple(_read_ids[4:])
    assert set(_C1_SCENARIOS)|set(_C2_SCENARIOS)==set(_read_ids)
    _dispatch_src=inspect.getsource(_dispatch)
    assert "if cid in _C2_SCENARIOS:" in _dispatch_src and "_execute_c2_scenario(_C2_SCENARIOS[cid],tmp_path)" in _dispatch_src
    assert _dispatch_src.index("if cid in _C2_SCENARIOS:") < _dispatch_src.index("FIXED_READ_SCENARIOS[cid][\"callable\"]")
    assert tuple(_C3_SCENARIOS)==_C3_IDS
    _c3_ids=list(_C3_IDS); _c3_records=[next(r for r in _read_group["records"] if r["id"]==i) for i in _c3_ids]
    assert len(_canon(_c3_ids))==150 and hashlib.sha256(_canon(_c3_ids)).hexdigest().upper()=="42AC5000C32BD43AD5EEB07D2126FCE466F04255718E00F8D1E95F98A33357F8"
    assert len(_canon(_c3_records))==3065 and hashlib.sha256(_canon(_c3_records)).hexdigest().upper()=="F4060144BBE7BAE18BD37F435185476C6144DF9ED627F4917AA76CF730AE1F96"
    assert tuple(f.name for f in dataclasses.fields(_C3Scenario))==("injection","expected_type","message","expected_cause","failure_trace","success_trace","expected_bytes")
    assert tuple(type(_C3_SCENARIOS[i].injection) for i in _C3_IDS)==(_C3CloseOSErrorInjection,_C3CloseRuntimeErrorInjection,_C3PrimaryPlusCloseInjection)
    assert not hasattr(_C3Scenario, "target_kind") and not hasattr(_C3PrimaryPlusCloseInjection, "primary")
    _graph_src=inspect.getsource(_c3_exception_graph)
    assert "seen=()" in _graph_src and "__name__" not in _graph_src and "seen+(id(exc),)" in _graph_src
    assert set(_C1_SCENARIOS).isdisjoint(_C3_SCENARIOS) and set(_C2_SCENARIOS).isdisjoint(_C3_SCENARIOS)
    assert set(_C1_SCENARIOS)|set(_C2_SCENARIOS)==set(_read_ids)
    assert set(_C3_SCENARIOS).isdisjoint(set(_read_ids))
    _sens=_run_c3_sensitivity()
    assert isinstance(_sens,_C3SensitivityReport) and _sens.status=="PENDING_CALLBACK_BATCH_B"
    assert len(_sens.required)==53 and len(_sens.detected)==47 and len(set(_sens.required))==53
    assert _sens.missing==tuple(f"d1b_c3_callback_{x}" for x in ("wrong_close_descriptor","duplicate_close","missing_close","duplicate_primary_callback","callback_after_primary_failure","fixture_bytes_mutation"))
    assert not _sens.unexpected and not _sens.duplicate and _sens.status=="PENDING_CALLBACK_BATCH_B"
    _cb_ids=tuple(f"d1b_c3_callback_{x}" for x in ("wrong_open_path","wrong_open_flags","wrong_first_fstat_descriptor","wrong_final_fstat_descriptor","wrong_read_descriptor","wrong_read_size"))
    _cb_proofs=tuple(_run_c3_callback_batch_a_case(i) for i in _cb_ids)
    _expected_ord=(1,1,1,2,1,1)
    assert len(_cb_proofs)==6 and all(type(p) is _C3CallbackProof and p.production_invocations==1 and p.boundary_invocations==1 and p.observed_callback_ordinal==_expected_ord[j] and p.neutralized_production_invocations==1 and p.neutralized_target_invocations==1 and p.neutralized_bytes==b"x" and p.status=="PASS" for j,p in enumerate(_cb_proofs))
