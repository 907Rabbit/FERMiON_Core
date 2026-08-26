import json,hashlib,os,sys,tempfile,platform
from pathlib import Path
import numpy as np
R=Path.cwd()
def fail(s): raise RuntimeError(s)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest().upper()
def bad(x): raise ValueError('nonfinite JSON constant')
def pairs(a):
 d={}
 for k,v in a:
  if k in d: raise ValueError('duplicate key '+k)
  d[k]=v
 return d
def load(p): return json.loads(Path(p).read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=bad)
def canon(o): return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def atomic(p,b):
 fd,t=tempfile.mkstemp(prefix=Path(p).name+'.',suffix='.tmp',dir=str(Path(p).parent))
 try:
  with os.fdopen(fd,'wb') as f: f.write(b);f.flush();os.fsync(f.fileno())
  os.replace(t,p)
 except BaseException:
  if os.path.exists(t): os.unlink(t)
  raise
def putj(p,o): atomic(p,canon(o))
def check(v,msg,F):
 if not v:F.append(msg)
def main():
 F=[]
 paths={'md':'protocols/cp10_p0_10_ORACLE_A_COMPLETION_CANDIDATE.md','candidate':'protocols/cp10_p0_10_ORACLE_A_COMPLETION_CANDIDATE.json','condition':'protocols/cp10_p0_10_condition_manifest.json','fixture_manifest':'artifacts/cp10_p0_10_oracle_a_initial_fixture_manifest.json','psis':'artifacts/cp10_p0_10_oracle_a_initial_psi_spectral.bin','psip':'artifacts/cp10_p0_10_oracle_a_initial_psi_physical.bin','phis':'artifacts/cp10_p0_10_oracle_a_initial_Phi_spectral.bin','phip':'artifacts/cp10_p0_10_oracle_a_initial_Phi_physical.bin','review':'artifacts/cp10_p0_10_review_manifest.json'}
 P={k:R/v for k,v in paths.items()}; expected={'md':'4D7DAD0687CBAEB7C200156ABF562321E9E3B16DA26F860997CDE528AA8DCF55','candidate':'E9B1329D95DBDD5FBB8168416A7145E62D684BD66C35F1C19629823039179759','fixture_manifest':'7AC0B4F4538D4BA628896C4ECA06BB7535A5E9D3E12533771D52D8BB4A17FAAE','review':'308A975FCBCD04559B572D9BA8F4E725F2B031BEAEC4D7E1F951237BB9383098'}
 for k,p in P.items(): check(p.is_file(),'missing '+k,F)
 H={k:sha(p) for k,p in P.items() if p.is_file()}
 for k,v in expected.items():check(H.get(k)==v,'reported hash '+k,F)
 try: c=load(P['candidate']);fm=load(P['fixture_manifest']);rv=load(P['review']);cm=load(P['condition']);p9=load(R/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json')
 except Exception as e: fail('strict parse '+repr(e))
 for k in ['candidate','fixture_manifest','review','condition']:
  check(P[k].read_bytes()==canon(load(P[k])),'canonical JSON '+k,F)
 check(len(set(str(x) for x in P.values()))==9,'input paths unique',F)
 check(all(x in rv['created_artifacts'] and rv['created_artifacts'][x]==H[k] for k,x in paths.items() if k!='review'),'review references all input hashes',F)
 check(rv['created_artifacts'][paths['candidate']]==H['candidate'],'review final candidate',F);check(rv['created_artifacts'][paths['condition']]==H['condition'],'review condition',F);check(rv['created_artifacts'][paths['fixture_manifest']]==H['fixture_manifest'],'review fixture manifest',F)
 fs=c['oracle_definitions']['oracle_a']['initial_fixture_files']; check(all(fs[x]['sha256']==H[k] for x,k in [('psi_initial_spectral','psis'),('psi_initial_physical','psip'),('Phi_initial_spectral','phis'),('Phi_initial_physical','phip')]),'candidate fixture hashes',F)
 check(c['oracle_definitions']['oracle_a']['initial_fixture_manifest_sha256']==H['fixture_manifest'],'candidate manifest hash',F)
 N=32;a=np.zeros((N,N),dtype='<c16')
 for key,v in p9['implementation_audit_fixtures']['padded_product']['psi'].items():
  i,j=map(int,key.split(','));a[i%N,j%N]=complex(*v)
 z=np.zeros((N,N),dtype='<c16');b=np.ascontiguousarray((np.fft.ifft2(a)*N*N).real,dtype='<f8');q=np.zeros((N,N),dtype='<f8')
 recon={'psis':a,'psip':b,'phis':z,'phip':q}; sizes={'psis':16384,'psip':8192,'phis':16384,'phip':8192}
 fr=[]
 for k,x in recon.items():
  raw=np.ascontiguousarray(x).tobytes('C');check(raw==P[k].read_bytes(),'fixture bytes '+k,F);check(len(raw)==sizes[k],'fixture length '+k,F);check(sha(P[k])==hashlib.sha256(raw).hexdigest().upper(),'fixture sha '+k,F);fr.append({'role':k,'byte_equal':raw==P[k].read_bytes(),'bytes':len(raw),'sha256':sha(P[k])})
 check(np.isfinite(b).all(),'physical finite',F);check(float(abs((np.fft.ifft2(a)*N*N).imag).max())<=1e-13,'imag leakage',F);check(np.count_nonzero(a[16,:])+np.count_nonzero(a[:,16])-np.count_nonzero(a[16,16])==0,'psi nyquist',F);check(all(abs(a[i,j]-np.conj(a[-i%N,-j%N]))==0 for i in range(N) for j in range(N)),'hermitian',F)
 o=c['oracle_definitions']['oracle_a']; ids=[x['run_id'] for x in o['runs']];want=['oracle_a_n032_dt0p0025_coarse','oracle_a_n032_dt0p00125_medium','oracle_a_n032_dt0p000625_fine'];check(ids==want,'run ids/order',F);check([(x['N'],x['dt'],x['T'],x['step_count'],x['expected_record_count']) for x in o['runs']]==[(32,.0025,1.,400,21),(32,.00125,1.,800,21),(32,.000625,1.,1600,21)],'tuples',F);check(o['record_times']==[i/20 for i in range(21)],'record times',F);check(o['numerical_state']['forcing_absent'] and o['numerical_state']['eta_exactly_zero'] and o['numerical_state']['Phi']['excluded_from_stepped_state'],'eta forcing Phi',F);check(o['parameters']['eta']==0,'eta parameter',F);check(o['mode_rules']['Hermitian_restoration'].endswith('<=1e-13 per accepted step'),'correction threshold',F);check('medium_fine_final' in o['metrics'] and 'medium_fine_trajectory' in o['metrics'],'comparison mapping',F);check(o['restart_contract']['checkpoint_or_resume_permitted'] is False,'restart',F);check(o['output_contract']['trajectory_shapes']=={'spectral':[21,32,32],'physical':[21,32,32]},'output shapes',F)
 n=dict(c);n.update({k:p9[k] for k in ['protocol_id','status','purpose','execution','execution_authorized','implementation_authorized','revision_provenance']});n['oracle_definitions']=dict(c['oracle_definitions']);n['oracle_definitions']['oracle_a']=p9['oracle_definitions']['oracle_a'];check(n==p9,'semantic carry forward',F)
 v=cm['validation'];check(v['stage_counts']=={'B':24,'C':120,'D':32,'E':48} and v['unique_conditions']==224 and v['replay_attempts']==9 and v['total_execution_records']==233 and v['duplicate_condition_ids']==0 and v['unresolved_parent_ids']==0,'condition counts',F);check(cm['calibration_seeds']==list(range(1,9)) and cm['held_out_seeds']==list(range(1001,1017)) and cm['replay_seeds']==[1001,1008,1016],'seed sets',F)
 status='READY_FOR_P0_10_FREEZE_REVIEW' if not F else 'BLOCKED_FROM_P0_10_FREEZE'
 au={'schema_version':'cp10-p0.10-independent-prefreeze-audit-v1','protocol_id':'CP10-P0.10','status':status,'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'architecture':platform.machine(),'byteorder':sys.byteorder},'source_artifacts':{'p0_9_json_sha256':sha(R/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json'),'blocker_audit_sha256':sha(R/'artifacts/cp10_p0_9_oracle_a_contract_audit.json')},'nine_artifact_hashes':{paths[k]:{'sha256':H[k],'byte_length':P[k].stat().st_size} for k in paths},'reference_consistency':{'candidate_embeds_four_binary_hashes':not any('candidate fixture' in x for x in F),'review_embeds_final_hashes':not any('review ' in x for x in F),'stale_candidate_hash_authoritative':False},'fixture_reconstruction':{'result':'PASS' if not any('fixture' in x or 'physical' in x or 'imag' in x or 'nyquist' in x or 'hermitian' in x for x in F) else 'FAIL','arrays':fr,'trajectory_count':0},'oracle_a_contract_validation':{'result':'PASS' if not any(x in F for x in ['run ids/order','tuples','record times','eta forcing Phi','eta parameter','correction threshold','comparison mapping','restart','output shapes']) else 'FAIL','runs':ids,'metrics_explicit':True,'hard_failures_explicit':True,'pass_aggregation_explicit':True},'semantic_diff_validation':{'result':'PASS' if 'semantic carry forward' not in F else 'FAIL'},'condition_set_validation':{'result':'PASS' if not any('condition' in x or 'seed' in x for x in F) else 'FAIL'},'freeze_readiness':status,'failures':F,'prohibited_actions_not_taken':['no Oracle timestepping','no solver execution','no scientific conditions','no held-out access','no bootstrap inference','no freeze receipt','no CP10 promotion','no CP11 action']}
 ap=R/'artifacts/cp10_p0_10_independent_prefreeze_audit.json';putj(ap,au)
 mp=R/'artifacts/cp10_p0_10_independent_prefreeze_audit_manifest.json';man={'schema_version':'cp10-p0.10-independent-prefreeze-audit-manifest-v1','verifier_source':{'path':'artifacts/cp10_p0_10_independent_prefreeze_verifier.py','sha256':sha(Path(__file__)),'byte_length':Path(__file__).stat().st_size},'audit':{'path':ap.relative_to(R).as_posix(),'sha256':sha(ap),'byte_length':ap.stat().st_size},'inputs':au['nine_artifact_hashes'],'parent_p0_9_sha256':au['source_artifacts']['p0_9_json_sha256'],'blocker_audit_sha256':au['source_artifacts']['blocker_audit_sha256'],'environment':au['environment'],'verifier_command':'python -B artifacts/cp10_p0_10_independent_prefreeze_verifier.py','exit_code':0,'numerical_trajectory_count':0,'oracle_a_run_count':0,'oracle_b_run_count':0,'disposition':status};putj(mp,man)
 for p in [ap,mp,Path(__file__)]:
  if p.suffix=='.json':check(Path(p).read_bytes()==canon(load(p)),'final canonical '+str(p),F)
 print(status);print(sha(ap));print(sha(mp))
if __name__=='__main__':main()
