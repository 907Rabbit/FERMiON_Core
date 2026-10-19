import argparse, copy, hashlib, json, math, os, pathlib, sys, tempfile
import mpmath as mp
import numpy as np

HERE=pathlib.Path(__file__).resolve().parent
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()+b'\n'
def load(p):
 def hook(a):
  d={}
  for k,v in a:
   if k in d: raise ValueError('duplicate key: '+k)
   d[k]=v
  return d
 return json.loads(p.read_text(encoding='utf8'),object_pairs_hook=hook,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON number')))
def digest(p):
 b=p.read_bytes();return hashlib.sha256(b).hexdigest().upper(),len(b)
def add(g,i,o,c,t,p): g.append({'id':i,'observed':o,'criterion':c,'tolerance':t,'passed':bool(p)})
def frac(x):
 if not isinstance(x['numerator'],int) or not isinstance(x['denominator'],int) or not x['denominator']: raise ValueError('invalid rational')
 return x['numerator']/x['denominator']
def rel(a,b): return abs(a-b)/abs(a) if a else abs(b)
def finite(x):
 if isinstance(x,dict): return all(finite(v) for v in x.values())
 if isinstance(x,(list,tuple)): return all(finite(v) for v in x)
 return not isinstance(x,(float,np.floating)) or math.isfinite(float(x))
def core(s,initial):
 g=copy.deepcopy(initial);t=s['validation_tolerances'];c=s['validation_contract'];w=s['background']['warp_parameters'];h=s['higgs_kernel']['parameters']
 o,l,q,k=(frac(w[z]) for z in ('overall','log_cosh_coefficient','sech_squared_coefficient','constant')); e,z,p=h['warp_exponent'],h['center'],h['sech_power']
 lo,hi=c['reference_domain'];dx=c['numpy_spacing'];ws=c['tail_cutoffs']
 if ws!=c['finite_domain_convergence_domains'] or not(lo<0<hi and dx>0 and all(lo<W<hi for W in ws)): raise ValueError('invalid numerical contract')
 x=np.linspace(lo,hi,round((hi-lo)/dx)+1);actual=float(x[1]-x[0]);add(g,'reference_grid_endpoint_alignment',[float(x[0]),float(x[-1])],'equals reference_domain',None,x[0]==lo and x[-1]==hi);add(g,'reference_grid_spacing',actual,'equals numpy_spacing',dx,math.isclose(actual,dx,rel_tol=0,abs_tol=1e-12))
 def A(v): return o*(l*np.log(np.cosh(v))+q/np.cosh(v)**2+k)
 def Ap(v): return o*(l*np.tanh(v)-2*q*np.tanh(v)/np.cosh(v)**2)
 def R12(a): return np.array([[math.cos(a),-math.sin(a),0],[math.sin(a),math.cos(a),0],[0,0,1.]])
 def R23(a): return np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
 mats={};checks={}
 for n,sec in s['sectors'].items():
  r1,r2=R12(sec['angles']['alpha']),R23(sec['angles']['beta']);u=r1@r2;y=np.diag(sec['Y']);m=u@np.diag(sec['D'])@u.T
  for name,v in [('R12',r1),('R23',r2),('U',u)]:
   a=float(np.max(abs(v.T@v-np.eye(3))));add(g,f'{name}_{n}',a,'<= tolerance',t['rotation_orthogonality_max_abs'],a<=t['rotation_orthogonality_max_abs'])
  for name,v in [('M',m),('Y',y)]:
   a=float(np.max(abs(v-v.T)));add(g,f'{name}_{n}_symmetry',a,'<= tolerance',t['matrix_symmetry_max_abs'],a<=t['matrix_symmetry_max_abs'])
  ey=np.linalg.eigvalsh(y);bp=np.linalg.eigvalsh(m+y+s['asymptotic']['B_plus_shift']*np.eye(3));bm=np.linalg.eigvalsh(m-y+s['asymptotic']['B_minus_shift']*np.eye(3));cm=m@y-y@m;cr=float(np.linalg.norm(cm)/(np.linalg.norm(m)*np.linalg.norm(y)))
  add(g,f'Y_{n}_positive',float(min(ey)),'>= tolerance',t['Y_min_eigenvalue'],min(ey)>=t['Y_min_eigenvalue']);add(g,f'B_plus_{n}',float(min(bp)),'>= tolerance',t['asymptotic_sign_margin_min'],min(bp)>=t['asymptotic_sign_margin_min']);add(g,f'B_minus_{n}',float(-max(bm)),'>= tolerance',t['asymptotic_sign_margin_min'],-max(bm)>=t['asymptotic_sign_margin_min']);add(g,f'commutator_{n}',cr,'>= tolerance',t['commutator_relative_min'],cr>=t['commutator_relative_min'])
  mats[n]={'R12':r1.tolist(),'R23':r2.tolist(),'U':u.tolist(),'Y':y.tolist(),'M':m.tolist()};checks[n]={'Y_eigenvalues':ey.tolist(),'B_plus_eigenvalues':bp.tolist(),'B_minus_eigenvalues':bm.tolist(),'commutator_relative':cr}
 samples=np.array(c['A0prime_sample_points']);step=c['A0prime_finite_difference_step'];fd=float(np.max(abs((A(samples+step)-A(samples-step))/(2*step)-Ap(samples))));points=np.r_[x,samples,c['endpoint_positions']]
 add(g,'A0_all_values_finite',bool(np.isfinite(A(points)).all()),'all finite',None,bool(np.isfinite(A(points)).all()));add(g,'A0prime_all_values_finite',bool(np.isfinite(Ap(points)).all()),'all finite',None,bool(np.isfinite(Ap(points)).all()));add(g,'A0prime_finite_difference',fd,'<= tolerance',t['A0_derivative_fd_max_abs'],fd<=t['A0_derivative_fd_max_abs'])
 for pos,expect,label in [(c['endpoint_positions'][0],-o*l,'negative'),(c['endpoint_positions'][1],o*l,'positive')]:
  a=float(abs(Ap(pos)-expect));add(g,'A0prime_'+label+'_endpoint',a,'<= tolerance',t['A0_asymptotic_derivative_max_abs'],a<=t['A0_asymptotic_derivative_max_abs'])
 yn=np.exp(2*e*A(x))/np.cosh(x-z)**(2*p);ni=float(np.trapezoid(yn,x));nn=float(1/math.sqrt(ni));old=mp.mp.dps
 try:
  with mp.workdps(c['precision_decimal_digits']):
   mo,ml,mq,mk=(mp.mpf(str(v)) for v in (o,l,q,k));me,mz,mpow=(mp.mpf(str(v)) for v in (e,z,p))
   def f(v): return mp.exp(2*me*mo*(ml*mp.log(mp.cosh(v))+mq/mp.cosh(v)**2+mk))/mp.cosh(v-mz)**(2*mpow)
   bs=sorted({mp.mpf(str(lo)),mp.mpf('0'),mp.mpf(str(hi)),*[mp.mpf(str(v)) for W in ws for v in (-W,W)]});I=sum(mp.quad(f,[a,b]) for a,b in zip(bs,bs[1:]));N=1/mp.sqrt(I);by={}
   for W in ws:
    mw=mp.mpf(str(W));mi=mp.quad(f,[-mw,0,mw]);mt=mp.quad(f,[mp.mpf(str(lo)),-mw])+mp.quad(f,[mw,mp.mpf(str(hi))]);nf=float(np.trapezoid(yn[(x>=-W)&(x<=W)],x[(x>=-W)&(x<=W)]));nt=float(np.trapezoid(yn[x<=-W],x[x<=-W])+np.trapezoid(yn[x>=W],x[x>=W]));by[str(int(W))]={'mp_integral':mi,'mp_tail':mt,'numpy_integral':nf,'numpy_tail':nt,'convergence':rel(I,mi),'tail_agreement':rel(mt,mp.mpf(str(nt)))}
   full,nhagree,norm=rel(I,mp.mpf(str(ni))),rel(N,mp.mpf(str(nn))),abs(N*mp.sqrt(I)-1);okI,okN=bool(mp.isfinite(I)),bool(mp.isfinite(N))
 finally: restored=mp.mp.dps==old;mp.mp.dps=old
 add(g,'h_reference_integral_finite',okI,'finite',None,okI);add(g,'h_reference_integral_positive',float(I),'> 0',None,I>0);add(g,'h_Nh_finite',okN,'finite',None,okN);add(g,'h_normalization',float(norm),'<= tolerance',t['h_normalization_max_abs'],norm<=t['h_normalization_max_abs']);add(g,'h_mp_numpy_full_integral_agreement',float(full),'<= tolerance',t['high_precision_numpy_full_relative_error_max'],full<=t['high_precision_numpy_full_relative_error_max']);add(g,'h_mp_numpy_Nh_agreement',float(nhagree),'<= tolerance',t['high_precision_numpy_Nh_relative_error_max'],nhagree<=t['high_precision_numpy_Nh_relative_error_max'])
 for W in ws:
  key=str(int(W));v=by[key];add(g,f'h_W{key}_convergence',float(v['convergence']),'<= tolerance',t['h_finite_domain_relative_error_max_by_W'][key],v['convergence']<=t['h_finite_domain_relative_error_max_by_W'][key]);add(g,f'h_W{key}_mp_tail',float(v['mp_tail']/I),'<= tolerance',t['h_tail_fraction_max_by_W'][key],v['mp_tail']/I<=t['h_tail_fraction_max_by_W'][key]);add(g,f'h_W{key}_numpy_tail',float(v['numpy_tail']/ni),'<= tolerance',t['h_tail_fraction_max_by_W'][key],v['numpy_tail']/ni<=t['h_tail_fraction_max_by_W'][key]);add(g,f'h_W{key}_tail_method_agreement',float(v['tail_agreement']),'<= tolerance',t['high_precision_numpy_tail_relative_error_max'],v['tail_agreement']<=t['high_precision_numpy_tail_relative_error_max'])
 out={'benchmark_id':s['benchmark_id'],'gates':g,'matrices':mats,'checks':checks,'A0prime_finite_difference_max_error':fd,'h_reference_integral':float(I),'h_reference_Nh':float(N),'h_numpy_integral':ni,'h_numpy_Nh':nn,'h_by_W':{a:{b:float(c) for b,c in v.items()} for a,v in by.items()}}
 add(g,'mpmath_global_precision_restored',restored,'restored',None,restored);add(g,'recursive_computed_value_finiteness',finite(out),'all finite',None,finite(out));return out
def verify(r,bind):
 q=dict(r);h=q.pop('result_payload_sha256',None)
 if h!=hashlib.sha256(canon(q)).hexdigest().upper(): raise ValueError('payload hash mismatch')
 if (r.get('spec_sha256'),r.get('spec_bytes'),r.get('validator_sha256'),r.get('validator_bytes'))!=bind: raise ValueError('binding mismatch')
def write(out,r,bind):
 q=dict(r);q.pop('result_payload_sha256',None);r['result_payload_sha256']=hashlib.sha256(canon(q)).hexdigest().upper();raw=canon(r);fd,name=tempfile.mkstemp(prefix='.'+out.name+'.',suffix='.tmp',dir=out.parent);tmp=pathlib.Path(name)
 try:
  with os.fdopen(fd,'wb') as f:f.write(raw)
  v=load(tmp);verify(v,bind)
  if canon(v)!=tmp.read_bytes() or tmp.read_bytes()!=raw: raise ValueError('temporary canonical byte identity failed')
  os.replace(tmp,out);v=load(out);verify(v,bind)
  if canon(v)!=out.read_bytes(): raise ValueError('final canonical byte identity failed')
 finally:
  if tmp.exists():tmp.unlink()
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--spec',type=pathlib.Path,default=HERE/'matrix_profile_benchmark_spec.json');ap.add_argument('--output',type=pathlib.Path,default=HERE/'matrix_profile_benchmark_validation.json');a=ap.parse_args(argv)
 try:
  s=load(a.spec);ss,sb=digest(a.spec);src=pathlib.Path(__file__).resolve();vs,vb=digest(src);before=canon(s);c=s['validation_contract'];t=s['validation_tolerances'];g=[];add(g,'strict_spec_parse',True,'strict parse',None,True);add(g,'contract_version',c.get('version'),"equals '2'",None,c.get('version')=='2');add(g,'finite_values_required',t.get('finite_values_required'),'is true',True,t.get('finite_values_required') is True);add(g,'canonical_recomputation_required',t.get('canonical_recomputation_required'),'is true',True,t.get('canonical_recomputation_required') is True)
  for n,e in [('sort_keys',True),('separators',[',',':']),('ensure_ascii',False),('allow_nan',False)]:add(g,'canonical_'+n,c.get('canonical_serialization',{}).get(n),'equals required setting',e,c.get('canonical_serialization',{}).get(n)==e)
  add(g,'validator_filename_binding',src.name,'equals expected filename',c.get('expected_validator_filename'),src.name==c.get('expected_validator_filename'));add(g,'validator_sha256_binding',vs,'equals expected SHA-256',c.get('expected_validator_sha256'),vs==c.get('expected_validator_sha256'))
  p1=core(json.loads(canon(s)),g);p2=core(json.loads(canon(s)),g);same=canon(p1)==canon(p2);add(p1['gates'],'core_recomputation_canonical_identity',same,'canonical bytes identical',None,same);add(p1['gates'],'input_spec_unchanged',canon(s)==before,'unchanged',None,canon(s)==before);ids=[x['id'] for x in p1['gates']];add(p1['gates'],'gate_ids_unique',len(ids),'no duplicate IDs',None,len(ids)==len(set(ids)));add(p1['gates'],'payload_hash_prewrite_verification',True,'verified before write',None,True);add(p1['gates'],'temporary_result_strict_reopen',True,'strictly reopened before replace',None,True);add(p1['gates'],'temporary_result_payload_hash_verification',True,'verified before replace',None,True);add(p1['gates'],'temporary_result_binding_verification',True,'verified before replace',None,True);add(p1['gates'],'temporary_result_canonical_byte_identity',True,'verified before replace',None,True);status='PASS' if all(x['passed'] for x in p1['gates']) else 'FAIL';r={'spec_sha256':ss,'spec_bytes':sb,'validator_sha256':vs,'validator_bytes':vb,'payload':p1,'gates':p1['gates'],'status':status};write(a.output,r,(ss,sb,vs,vb));return 0 if status=='PASS' else 1
 except Exception as e: print('validator error: '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
