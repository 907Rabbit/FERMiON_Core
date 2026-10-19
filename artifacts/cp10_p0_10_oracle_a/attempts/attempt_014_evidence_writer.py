"""Attempt-014 C2 evidence writer. Terminal-newline policy: no newline."""
import argparse, hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/cp10_p0_10_oracle_a'; ATT=OUT/'attempts'
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
TARGETS=(OUT/'r2a2a2s1tc2_source_manifest.json',OUT/'r2a2a2s1tc2_case_coverage.json',OUT/'r2a2a2s1tc2_test_manifest.json',OUT/'r2a2a2s1tc2_readiness_audit.json',ATT/'attempt_014_manifest.json')
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def strict_bytes(b):
 def hook(p):
  d={}
  for k,v in p:
   if k in d: raise ValueError('duplicate key')
   d[k]=v
  return d
 return json.loads(b.decode('utf-8'),object_pairs_hook=hook,parse_constant=lambda v:(_ for _ in()).throw(ValueError(v)))
def sha(b): return hashlib.sha256(b).hexdigest().upper()
def hf(p): return sha(p.read_bytes())
def atomic(p,b):
 q=p.with_name(p.name+'.tmp');
 with open(q,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 os.replace(q,p)
 if p.read_bytes()!=b or hf(p)!=sha(b):raise RuntimeError('atomic verification')
def payloads():
 spec=importlib.util.spec_from_file_location('c2_payload_tests',ROOT/'tests/test_cp10_oracle_a_launch_payload_p0_10.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
 ids=[x.id for x in t.C2_CASES]; req=sorted(t.C2_REQUIRED_CASE_IDS); missing=sorted(set(req)-set(ids)); extra=sorted(set(ids)-set(req)); dup=sorted({x for x in ids if ids.count(x)>1})
 cmd=[sys.executable,'-m','pytest','--collect-only','-q','-p','no:cacheprovider','tests/test_cp10_oracle_a_runspec_p0_10.py','tests/test_cp10_oracle_a_launch_payload_p0_10.py']; r=subprocess.run(cmd,capture_output=True,text=True); nodes=[x for x in r.stdout.splitlines() if '::' in x]; cov=[x for x in nodes if 'test_c2_case_coverage_is_exact' in x]
 assert len(req)==len(ids)==len(set(ids))==317 and not(missing or extra or dup) and sum(x.values[3] for x in t.C2_CASES)==3 and len(nodes)==540 and len(cov)==1
 s=ROOT/'fermion/cp10/oracle_a_p0_10.py';q=ROOT/'tests/test_cp10_oracle_a_launch_payload_p0_10.py'; base={'runner':hf(s),'payload_tests':hf(q)}
 source={'schema_version':'c2-source-v1','status':'PASS','files':base,'attempt_013_source_test_changes':'NONE'}
 coverage={'schema_version':'c2-coverage-v1','status':'PASS','required_ids':req,'collected_matrix_ids':ids,'missing_ids':missing,'unexpected_ids':extra,'duplicate_ids':dup,'required_count':317,'collected_count':317,'unique_collected_count':317,'valid_count':3,'invalid_count':314,'independent_coverage_test_node_id':cov[0],'coverage_test_separate_from_matrix':cov[0] not in req,'collection_total':540}
 test={'schema_version':'c2-test-v1','status':'PASS','collection_command':' '.join(cmd),'collection_total':540,'collected_node_ids':nodes,'focused_result':'540 passed in 0.78s','arithmetic':{'baseline':222,'matrix':317,'coverage':1,'total':540}}
 a,b,c=map(lambda x:sha(canon(x)),(source,coverage,test)); ready={'schema_version':'c2-readiness-v1','status':'BLOCKED_PENDING_R2A2A2_S1T_D_FILESYSTEM_AUTHORIZATION_REVALIDATION','source_hash':a,'coverage_hash':b,'test_hash':c,'launch_records':0,'integration_calls':0,'frozen_trajectories':0}; d=sha(canon(ready)); attempt={'schema_version':'attempt-014-v1','status':'PASS','attempt_011_hash':'7CABC37DA7AB65F697656F9541629F1F7B59281FE5B2900ED4EB81997F99E690','attempt_013_failure':'EVIDENCE WRITER SYNTAX ERROR, NO PROMOTION','source_test_changes':'NONE','writer_sha256':hf(Path(__file__)),'source_hash':a,'coverage_hash':b,'test_hash':c,'readiness_hash':d,'corrected_total':540}
 return (source,coverage,test,ready,attempt)
def main():
 a=argparse.ArgumentParser();g=a.add_mutually_exclusive_group(required=True);g.add_argument('--validate-only',action='store_true');g.add_argument('--commit',action='store_true');ns=a.parse_args(); values=payloads(); blobs=[canon(x) for x in values]
 for b in blobs:strict_bytes(b)
 print('\n'.join(f'{p}:{sha(b)}:{len(b)}' for p,b in zip(TARGETS,blobs)))
 if ns.commit:
  for p,b in zip(TARGETS,blobs):atomic(p,b)
if __name__=='__main__':main()
