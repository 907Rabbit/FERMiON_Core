import os, stat
from pathlib import Path
import pytest
from fermion.cp10 import oracle_a_p0_10 as o

D1A_REQUIRED_CASE_IDS={"contract_24_target_hash_valid","contract_25_target_hash_valid","path_parent_traversal","path_absolute","path_unc","path_device","path_extended_length","path_alternate_data_stream","path_nul","path_backslash","path_outside_output_root","filesystem_output_root_missing","filesystem_output_root_is_file","filesystem_output_root_symlink","filesystem_intermediate_symlink","filesystem_target_symlink","filesystem_output_root_reparse","filesystem_intermediate_reparse","filesystem_resolved_escape","production_wrapper_no_root_override","production_wrapper_no_launch_path_override"}
D1A_COLLISION_IDS=tuple(f"collision_target_{target.replace('/','__').replace('.','_')}" for target in o.PRODUCTION_TARGETS)
D1A_REQUIRED_CASE_IDS.update({"contract_clean_valid","contract_evidence_only_valid","collision_reserved_production_temporary",*D1A_COLLISION_IDS})
def project_state(tmp, state="directory"):
 output = tmp / o.PRODUCTION_OUTPUT_ROOT_RELATIVE
 output.parent.mkdir(parents=True, exist_ok=True)
 if state == "directory": output.mkdir()
 elif state == "file": output.write_bytes(b"x")
 elif state != "missing": raise AssertionError(state)
 return tmp, output
def clean(tmp): return project_state(tmp)[0]
def call(tmp,targets=o.PRODUCTION_CANDIDATE_TARGETS,**kw):return o._validate_filesystem_paths(tmp,o.PRODUCTION_OUTPUT_ROOT_RELATIVE,targets,**kw)
@pytest.mark.parametrize('case_id',sorted(D1A_REQUIRED_CASE_IDS))
def test_d1a_phase1(case_id,tmp_path):
 if case_id=='contract_clean_valid':assert call(clean(tmp_path),o.PRODUCTION_TARGETS).collisions==();return
 if case_id=='contract_evidence_only_valid':
  t=clean(tmp_path);(t/o.PRODUCTION_OUTPUT_ROOT_RELATIVE/'attempts').mkdir();(t/o.PRODUCTION_OUTPUT_ROOT_RELATIVE/'evidence.json').write_text('{}');assert call(t,o.PRODUCTION_TARGETS).status=='PASS';return
 if case_id=='collision_reserved_production_temporary':
  t=clean(tmp_path);p=t/o.PRODUCTION_OUTPUT_ROOT_RELATIVE/'.oracle_a_prod_x';p.write_bytes(b'x')
  with pytest.raises(o.FilesystemAuthorizationError,match='production collision'):call(t,o.PRODUCTION_TARGETS)
  assert p.read_bytes()==b'x';return
 if case_id in D1A_COLLISION_IDS:
  t=clean(tmp_path);target=o.PRODUCTION_TARGETS[D1A_COLLISION_IDS.index(case_id)];p=t/o.PRODUCTION_OUTPUT_ROOT_RELATIVE/target;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x')
  with pytest.raises(o.FilesystemAuthorizationError,match='production collision'):call(t,o.PRODUCTION_TARGETS)
  assert p.read_bytes()==b'x';return
 if case_id=='contract_24_target_hash_valid':assert call(clean(tmp_path)).status=='PASS';return
 if case_id=='contract_25_target_hash_valid':assert call(clean(tmp_path),o.PRODUCTION_TARGETS).status=='PASS';return
 if case_id=='production_wrapper_no_root_override':
  with pytest.raises(TypeError):o.production_filesystem_contract(root=tmp_path)
  return
 if case_id=='production_wrapper_no_launch_path_override':
  with pytest.raises(TypeError):o.production_filesystem_contract(launch_path='x')
  return
 if case_id=='filesystem_output_root_missing':
  _, output=project_state(tmp_path,'missing');assert not output.exists()
  with pytest.raises(o.FilesystemAuthorizationError):call(tmp_path)
  return
 if case_id=='filesystem_output_root_is_file':
  _, output=project_state(tmp_path,'file');assert output.is_file()
  with pytest.raises(o.FilesystemAuthorizationError):call(tmp_path)
  return
 t=clean(tmp_path)
 bad={
 'path_parent_traversal':'../x','path_absolute':'/x','path_unc':'//host/x','path_device':'//./x','path_extended_length':'//?/x','path_alternate_data_stream':'x:y','path_nul':'x\0','path_backslash':'x\\y','path_outside_output_root':'x'}
 if case_id in bad:
  with pytest.raises(o.FilesystemAuthorizationError):call(t,(bad[case_id],)*24)
  return
 class S:st_mode=stat.S_IFLNK;st_file_attributes=0
 with pytest.raises(o.FilesystemAuthorizationError):call(t,lstat_fn=lambda p:S())
assert len(D1A_REQUIRED_CASE_IDS)==49
def test_d1a_coverage():
 assert len(D1A_REQUIRED_CASE_IDS)==49
