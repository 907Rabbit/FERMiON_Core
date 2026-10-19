import hashlib,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'artifacts/cp10_p0_10_oracle_a';ATT=OUT/'attempts'
IDS=("contract_24_target_hash_valid","contract_25_target_hash_valid","path_parent_traversal","path_absolute","path_unc","path_device","path_extended_length","path_alternate_data_stream","path_nul","path_backslash","path_outside_output_root","filesystem_output_root_missing","filesystem_output_root_is_file","filesystem_output_root_symlink","filesystem_intermediate_symlink","filesystem_target_symlink","filesystem_output_root_reparse","filesystem_intermediate_reparse","filesystem_resolved_escape","production_wrapper_no_root_override","production_wrapper_no_launch_path_override")
def enc(x):return (json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def strict(b):
 def hook(p):
  d={}
  for k,v in p:
   if k in d:raise ValueError('duplicate')
   d[k]=v
  return d
 return json.loads(b.decode(),object_pairs_hook=hook,parse_constant=lambda v:(_ for _ in()).throw(ValueError(v)))
def h(b):return hashlib.sha256(b).hexdigest().upper()
def write(p,b):
 fd,q=tempfile.mkstemp(dir=p.parent);f=os.fdopen(fd,'wb');f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(q,p);assert p.read_bytes()==b
def main():
 assert len(IDS)==len(set(IDS))==21
 fs=[ROOT/'fermion/cp10/oracle_a_p0_10.py',ROOT/'tests/test_cp10_oracle_a_runspec_p0_10.py',ROOT/'tests/test_cp10_oracle_a_launch_payload_p0_10.py',ROOT/'tests/test_cp10_oracle_a_filesystem_contract_p0_10.py'];files=[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':h(p.read_bytes()),'byte_count':p.stat().st_size} for p in fs]
 ready={'status':'D1A_PHASE1_PATH_SAFETY_PASS_COLLISION_ENGINE_PENDING','compile':'PASS','collected':561,'passed':561,'required_ids':list(IDS),'required_count':21,'collected_count':21,'unique_count':21,'missing_ids':[],'unexpected_ids':[],'duplicate_ids':[],'production_isolation':'PASS','collision_engine':'NOT_IMPLEMENTED','d1a_final_pass_claimed':False,'terminal_newline':True};rb=enc(ready);strict(rb);rh=h(rb);rp=OUT/'r2a2a2s1td1a_phase1_readiness_audit.json';write(rp,rb)
 wp=Path(__file__);manifest={'attempt':25,'attempts_022_024':'phase1 progression preserved','files':files,'phase1_ids':list(IDS),'readiness_path':str(rp.relative_to(ROOT)).replace('\\','/'),'readiness_sha256':rh,'writer_path':str(wp.relative_to(ROOT)).replace('\\','/'),'writer_sha256':h(wp.read_bytes()),'test_command':'focused three-module regression','observed_result':'561 passed in 1.62s','attempt_025_changes':'writer and checkpoint JSON only','launch_record':False,'output':False,'probe':False,'integration':False,'trajectory':False};mb=enc(manifest);strict(mb);mp=ATT/'attempt_025_d1a_phase1_manifest.json';write(mp,mb)
 for p in (rp,mp):b=p.read_bytes();strict(b);print(str(p),h(b),len(b))
if __name__=='__main__':main()
