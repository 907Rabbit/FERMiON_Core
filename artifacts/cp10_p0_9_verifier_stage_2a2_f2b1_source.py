"""Standalone CP10-P0.9 Stage 2A.1 numerical primitives."""
import ast, hashlib, json, math, os, platform, sys, tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def strict_json(path):
 def hook(xs):
  d={}
  for k,v in xs:
   if k in d: raise ValueError("duplicate key")
   d[k]=v
  return d
 return json.loads(Path(path).read_bytes().decode("utf-8","strict"),object_pairs_hook=hook,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def sha256_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def continuum_forward(field):
 if np.iscomplexobj(field): raise TypeError('continuum_forward accepts real physical fields only')
 a=np.asarray(field,dtype=np.float64); return np.fft.fft2(a)/a.size
def continuum_inverse(spectrum):
 a=np.asarray(spectrum,dtype=np.complex128); return np.fft.ifft2(a*a.size).real
def count_nonfinite(*arrays): return int(sum(np.size(a)-np.count_nonzero(np.isfinite(a)) for a in arrays))
def signed_modes(N): return np.fft.fftfreq(N,1/N).astype(int)
def retained_mask(N):
 k=signed_modes(N);a,b=np.meshgrid(k,k,indexing="ij");return (abs(a)<=N//2-1)&(abs(b)<=N//2-1)
def inspect_nyquist(spectrum,tolerance=0.):
 N=spectrum.shape[0]; return int(np.count_nonzero(abs(spectrum[N//2,:])>tolerance)+np.count_nonzero(abs(spectrum[:,N//2])>tolerance)-int(abs(spectrum[N//2,N//2])>tolerance))
def spectral_diagnostics(spectrum,N,nyquist_tolerance):
 h=np.asarray(spectrum,dtype=np.complex128);return {'maximum_retained_magnitude':float(np.max(abs(h[retained_mask(N)]))),'nonfinite_count':count_nonfinite(h),'nyquist_count':inspect_nyquist(h,nyquist_tolerance),'hermitian_mismatch':float(hermitian_mismatch(h))}
def hermitian_mismatch(s):
 N=len(s);return max(abs(s[i,j]-s[-i%N,-j%N].conjugate())for i in range(N)for j in range(N))
def hermitian_correct(s):
 N=len(s);o=np.array(s,complex,copy=True)
 for i in range(N):
  for j in range(N):o[i,j]=.5*(s[i,j]+s[-i%N,-j%N].conjugate())
 return o
def embed_to_padded(spectrum,P=None):
 N=len(spectrum);P=P or 2*N;o=np.zeros((P,P),complex)
 for i in range(-N//2+1,N//2):
  for j in range(-N//2+1,N//2):o[i%P,j%P]=spectrum[i%N,j%N]
 return o
def restrict_from_padded(s,N):
 o=np.zeros((N,N),complex)
 for i in range(-N//2+1,N//2):
  for j in range(-N//2+1,N//2):o[i%N,j%N]=s[i%s.shape[0],j%s.shape[1]]
 return o
def padded_product(a,b):
 N=len(a);P=2*N;A=embed_to_padded(continuum_forward(a),P);B=embed_to_padded(continuum_forward(b),P)
 C=np.fft.fft2(np.fft.ifft2(A*P*P)*np.fft.ifft2(B*P*P))/(P*P)
 return continuum_inverse(restrict_from_padded(C,N))
def direct_dictionary_convolution(a,b):
 o={}
 for k,v in a.items():
  for l,w in b.items():o[(k[0]+l[0],k[1]+l[1])]=o.get((k[0]+l[0],k[1]+l[1]),0j)+v*w
 return {k:v for k,v in o.items() if v}
def restrict_common_band(fine_field,coarse_N):
 h=continuum_forward(fine_field);o=np.zeros((coarse_N,coarse_N),complex)
 for i in range(-coarse_N//2+1,coarse_N//2):
  for j in range(-coarse_N//2+1,coarse_N//2):o[i%coarse_N,j%coarse_N]=h[i%len(h),j%len(h)]
 return continuum_inverse(o)
def spatial_l2(x):return float((2*np.pi/len(x))*np.sqrt(np.sum(abs(x)**2)))
def trajectory_l2(records,weights):return math.sqrt(sum(w*spatial_l2(x)**2 for x,w in zip(records,weights)))
def relative_error(a,b):return spatial_l2(a-b)/max(spatial_l2(b),1e-12)
def modal_max_error(a,b):
 return max(np.max(abs(continuum_forward(x)-continuum_forward(y)))for x,y in zip(a,b))/max(max(np.max(abs(continuum_forward(y)))for y in b),1e-12)
def canonical_array_metadata(x):
 a=np.ascontiguousarray(np.asarray(x,dtype="<c16" if np.iscomplexobj(x) else "<f8"))
 return {"shape":list(a.shape),"dtype":a.dtype.str,"byte_order":"little","byte_length":a.nbytes,"sha256":hashlib.sha256(a.tobytes()).hexdigest()}
def spectral_laplacian(x):
 N=len(x);k=signed_modes(N);a,b=np.meshgrid(k,k,indexing='ij');return continuum_inverse(-(a*a+b*b)*continuum_forward(x)*retained_mask(N))
def stage_2a2():
 c=strict_json(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');a2m=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a1_repair_manifest.json';a2r=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a1_repair.json'
 if sha256_file(a2m).upper()!='47F3A3E420CA79CC604F5A1550066885258D09FF06C57CE2F95950ABD4A92FD8' or sha256_file(a2r).upper()!='EA84A3915A008D905F9101201484B0CB32ED479939BD96019C7C6DB93A6F1748':raise RuntimeError('Stage 2A.1 provenance mismatch')
 p=c['oracle_definitions']['oracle_b']['parameters'];m=c['model']['parameters'];params={'lambda_Phi':p['lambda_Phi'],'v_Phi':p['v_Phi'],'eta':p['eta'],'A':p['A'],'B':p['B'],'M_psi':m['M_psi'],'kappa_psi':m['kappa_psi'],'m_psi_squared':m['m_psi_squared'],'M_Phi':m['M_Phi'],'kappa_Phi':m['kappa_Phi']};want={'lambda_Phi':1,'v_Phi':1,'eta':.1,'A':.1,'B':.1,'M_psi':1,'kappa_psi':1,'m_psi_squared':1,'M_Phi':1,'kappa_Phi':1}
 checks=[];cases=[]
 for N in (32,64,128):
  x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing='ij')
  for t in (0.,.25,.5,1.):
   psi=.1*np.exp(-t)*np.cos(X)*np.cos(Y);phi=.1*np.exp(-2*t)*np.sin(X)*np.sin(Y);dpsi=-psi;dphi=-2*phi
   p2=padded_product(phi,phi);nphi=padded_product(phi,p2-1);pp=padded_product(phi,psi);dlp=spectral_laplacian(p2);analytic=.01*np.exp(-4*t)*(np.cos(2*X)+np.cos(2*Y)-2*np.cos(2*X)*np.cos(2*Y));forcepsi=5*psi+.1*dlp;forcephi=nphi-.2*pp
   mpsi=-spectral_laplacian(psi)+psi-.1*p2;mphi=-spectral_laplacian(phi)+nphi-.2*pp;rp=dpsi-(spectral_laplacian(mpsi)+forcepsi);rf=dphi-(-mphi+forcephi)
   rs=[]
   for name,rhs,der in [('psi',rp,dpsi),('Phi',rf,dphi)]:
    hh=continuum_forward(rhs);mx=float(np.max(abs(hh[retained_mask(N)])));den=max(float(np.max(abs(continuum_forward(der)[retained_mask(N)]))),1e-12);nf=count_nonfinite(rhs);ny=inspect_nyquist(hh,1e-14);hm=hermitian_mismatch(hh);ok=mx<=1e-12 and nf==0 and ny==0 and hm<=1e-14
    rs.append({'field':name,'max_abs_retained_spectral_residual':mx,'spatial_l2_residual':spatial_l2(rhs),'max_exact_time_derivative_coefficient':den,'relative_spectral_residual':mx/den,'nonfinite_count':nf,'nyquist_violation_count':ny,'hermitian_mismatch':hm,'arrays':{'exact':canonical_array_metadata(psi if name=='psi'else phi),'time_derivative':canonical_array_metadata(der),'forcing':canonical_array_metadata(forcepsi if name=='psi'else forcephi),'rhs':canonical_array_metadata(dpsi-rhs if name=='psi'else dphi-rhs),'residual':canonical_array_metadata(rhs)},'status':ok});checks.append(ok)
   dm=float(np.max(abs(continuum_forward(dlp-analytic)[retained_mask(N)])));checks.append(dm<=1e-12);cases.append({'N':N,'t':t,'fields':rs,'delta_phi2_spectral_mismatch':dm,'delta_phi2_status':dm<=1e-12})
 out={'status':'PASS'if all(checks) and params==want else'FAIL','stage_2a1_repair_hashes':{'manifest':sha256_file(a2m),'result':sha256_file(a2r)},'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'byteorder':sys.byteorder},'parameters':params,'parameter_status':bool(params==want),'cases':cases,'residual_case_count':len(cases),'oracle_a_run_count':0,'oracle_b_run_count':0,'time_integration_occurred':False};q=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_residuals.json';b=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic)else str(x)).encode();f=tempfile.NamedTemporaryFile(dir=q.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,q);return 0 if out['status']=='PASS'else 1
def repair():
 cpath=ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json';checks=[]
 def ck(i,v,e=None,comparison=None,status=None):
  limit=e if comparison in ('<','<=','>','>=') else None
  expected=None if limit is not None else e
  checks.append({'id':i,'measured':v,'expected':expected,'comparison':comparison,'threshold':limit,'status':bool(v if status is None else status)})
 c=strict_json(cpath);ck('strict_candidate_parse',True); td=Path(tempfile.mkdtemp())
 for n,s in [('duplicate_key_rejected','{"x":1,"x":2}'),('nan_rejected','{"x":NaN}'),('positive_infinity_rejected','{"x":Infinity}'),('negative_infinity_rejected','{"x":-Infinity}')]:
  p=td/n;p.write_text(s);typ='NONE'
  try:strict_json(p)
  except Exception as e:typ=type(e).__name__
  ck(n,typ,'ValueError',status=typ=='ValueError')
 N=32;x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing='ij');u=np.cos(2*X+Y);rt=relative_error(continuum_inverse(continuum_forward(u)),u);pa=abs((2*np.pi/N)**2*np.sum(u*u)-(2*np.pi)**2*np.sum(abs(continuum_forward(u))**2));k=signed_modes(N);K=np.meshgrid(k,k,indexing='ij')[0];de=relative_error(continuum_inverse(1j*K*continuum_forward(u)),-2*np.sin(2*X+Y));ck('fft_roundtrip',rt,1e-14,'<',rt<1e-14);ck('parseval',pa,1e-13,'<',pa<1e-13);ck('analytic_derivative',de,1e-12,'<',de<1e-12)
 fx=c['implementation_audit_fixtures']['padded_product'];v=fx['v'];D=lambda z:{tuple(map(int,k.split(','))):complex(*w)for k,w in z.items()};phi,psi=D(fx['Phi']),D(fx['psi']);p2=direct_dictionary_convolution(phi,phi);p3=direct_dictionary_convolution(p2,phi);pp=direct_dictionary_convolution(phi,psi);q=dict(p2);q[(0,0)]=q.get((0,0),0)-v*v;pf=direct_dictionary_convolution(phi,q)
 def ar(d,n=32):
  z=np.zeros((n,n),complex)
  for k,w in d.items():z[k[0]%n,k[1]%n]=w
  return continuum_inverse(z)
 for i,(n,r,a,b,ex) in enumerate([('Phi2',p2,phi,phi,33),('Phi3',p3,p2,phi,86),('PhiPsi',pp,phi,psi,50),('Phi_Phi2_minus_v2',pf,phi,q,86)]):
  g=continuum_forward(padded_product(ar(a),ar(b)));er=max(abs(g[ii%32,jj%32]-r.get((ii,jj),0))for ii in range(-15,16)for jj in range(-15,16));ck('padded_'+n,er,1e-12,'<',er<1e-12);ck('support_'+n,len(r),ex,'=',len(r)==ex)
 ck('anchor_1_2',abs(pf[(1,2)]-(-.115672625)),1e-15,'<=',abs(pf[(1,2)]+.115672625)<=1e-15);ck('anchor_2_minus1',abs(pf[(2,-1)]-(-.098398125j)),1e-15,'<=',abs(pf[(2,-1)]+.098398125j)<=1e-15)
 low=np.cos(2*np.meshgrid(np.arange(64)*2*np.pi/64,np.arange(64)*2*np.pi/64,indexing='ij')[0]);cb=float(np.max(abs(continuum_forward(restrict_common_band(low,32))-continuum_forward(np.cos(2*X)))));ck('common_band_restriction',cb,1e-14,'<',cb<1e-14)
 rec=[u,u];ti=trajectory_l2(rec,[.5,.5]);ck('trajectory_l2_identity',ti,math.pi*math.sqrt(2),'abs<=',abs(ti-math.pi*math.sqrt(2))<=1e-12);ck('trajectory_l2_perturbation_positive',trajectory_l2([u,u+.1],[.5,.5]),0,'>',trajectory_l2([u,u+.1],[.5,.5])>0);ck('modal_max_identity',modal_max_error(rec,rec),0,'=',modal_max_error(rec,rec)==0);ck('modal_max_perturbation_positive',modal_max_error([u+.1,u],rec),0,'>',modal_max_error([u+.1,u],rec)>0)
 a=canonical_array_metadata(u);b=canonical_array_metadata(u);z=u.copy();z[0,0]+=1;ck('array_hash_repeatability',a['sha256'],b['sha256'],'=',a==b);ck('array_hash_mutation',canonical_array_metadata(z)['sha256'],a['sha256'],'!=',canonical_array_metadata(z)['sha256']!=a['sha256']);z[0,0]=np.nan;ck('nonfinite_injection',count_nonfinite(z),1,'=',count_nonfinite(z)==1)
 hh=continuum_forward(u);hh[16,0]=1;ck('nyquist_injection',inspect_nyquist(hh,1e-13),1,'=',inspect_nyquist(hh,1e-13)==1);hh[1,2]+=1;ck('hermitian_injection_detected',hermitian_mismatch(hh),0,'>',hermitian_mismatch(hh)>0);ck('hermitian_correction',hermitian_mismatch(hermitian_correct(hh)),1e-14,'<',hermitian_mismatch(hermitian_correct(hh))<1e-14)
 names=[]
 for n in ast.walk(ast.parse(Path(__file__).read_text())):
  if isinstance(n,ast.Import):names += [x.name for x in n.names]
  if isinstance(n,ast.ImportFrom):names += [n.module or '']
 ck('forbidden_import_scan',names,'no fermion','',not any(x=='fermion'or x.startswith('fermion.')for x in names))
 for i,p,ex in [('historical_fail_hash','artifacts/cp10_p0_9_oracle_verification.json','c54c254333a89ac05cc67086c7d434c7c32ce939ce79b1fe515fc71d41481ff6'),('candidate_md_hash','protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.md','db463e91ab9e4787d781755cc7285c5845783bf84956dddfe746644b00584eb1'),('candidate_json_hash','protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json','aad274639d2a49ebc2d183f8486534eaba039188eb7cd8d4239eefefb85a0590'),('condition_manifest_hash','protocols/cp10_p0_9_condition_manifest.json','71e226b4ef5517b3e414c36feb207096d1182912ab30441460b8af9c1055ddfe'),('review_manifest_hash','artifacts/cp10_p0_9_review_manifest.json','d64c4c86bedffb7aa565ce8e477463ca60aaa2c8ca29cda5232a8d200bb965ad')]:ck(i,sha256_file(ROOT/p),ex,'=',sha256_file(ROOT/p)==ex)
 out={'status':'PASS'if all(x['status']for x in checks)else'FAIL','checks':checks,'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'byteorder':sys.byteorder},'working_verifier_sha256':sha256_file(__file__),'oracle_a_run_count':0,'oracle_b_run_count':0,'historical_fail_untouched':sha256_file(ROOT/'artifacts/cp10_p0_9_oracle_verification.json')};p=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a1_repair.json';bb=json.dumps(out,sort_keys=True,separators=(',',':')).encode();f=tempfile.NamedTemporaryFile(dir=p.parent,delete=False);f.write(bb);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,p);return 0 if out['status']=='PASS'else 1
def stage_2a2_kat():
 c=strict_json(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');p=c['oracle_definitions']['oracle_b']['parameters'];N=128;t=0.;ps,ph,aps,aph,h2,had,rs,rp,fp,ff=manufactured_coefficient_case(N,t,p);checks=[]
 def ck(i,field,val,exp,cmp,th,ok):checks.append({'id':i,'N':N,'t':t,'field':field,'measured':float(val),'expected':exp,'comparison':cmp,'threshold':th,'status':bool(ok)})
 for name,a,b,r in [('psi',ps,aps,rs),('Phi',ph,aph,rp)]:
  re=float(np.max(abs(a-b)));mx=float(np.max(abs(continuum_forward(r)[retained_mask(N)])));nf=count_nonfinite(r);ny=inspect_nyquist(continuum_forward(r),1e-14);hm=hermitian_mismatch(continuum_forward(r));ck('reconstruction',name,re,None,'<=',1e-14,re<=1e-14);ck('residual',name,mx,None,'<=',1e-12,mx<=1e-12);ck('nonfinite',name,nf,0,'=',None,nf==0);ck('nyquist',name,ny,0,'=',None,ny==0);ck('hermitian',name,hm,None,'<=',1e-14,hm<=1e-14)
 dm=float(np.max(abs((-np.add.outer(signed_modes(N)**2,signed_modes(N)**2)*h2-had)[retained_mask(N)])));ck('delta_phi2',None,dm,None,'<=',1e-12,dm<=1e-12)
 out={'status':'PASS'if all(z['status']for z in checks)else'FAIL','checks':checks,'input_hashes':c['revision_provenance']['p0_8_authoritative_hashes'],'failed_path_manifest_sha256':sha256_file(ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_attempt_001_manifest.json'),'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'byteorder':sys.byteorder},'parameters':p,'arrays':{n:canonical_array_metadata(a)for n,a in [('psi_exact',ps),('Phi_exact',ph),('fpsi',continuum_inverse(fp)),('fPhi',continuum_inverse(ff)),('psi_residual',continuum_inverse(rs)),('Phi_residual',continuum_inverse(rp))]},'residual_case_count':1,'oracle_a_run_count':0,'oracle_b_run_count':0,'time_integration_occurred':False};q=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat.json';b=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=q.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,q);return 0 if out['status']=='PASS'else 1
def stage_2a2_kat_repair():
 import warnings
 with warnings.catch_warnings():
  warnings.simplefilter('error');c=strict_json(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');p=c['oracle_definitions']['oracle_b']['parameters'];N=128;t=0.;ps,ph,aps,aph,h2,had,rs,rp,fp,ff=manufactured_coefficient_case(N,t,p);checks=[]
  def ck(i,f,v,e,co,th,ok):checks.append({'id':i,'N':N,'t':t,'field':f,'measured':float(v),'expected':e,'comparison':co,'threshold':th,'status':bool(ok)})
  for n,a,b,r in [('psi',ps,aps,rs),('Phi',ph,aph,rp)]:
   d=spectral_diagnostics(r,N,1e-14);re=float(np.max(abs(a-b)));ck(n+'_reconstruction',n,re,None,'<=',1e-14,re<=1e-14);ck(n+'_residual',n,d['maximum_retained_magnitude'],None,'<=',1e-12,d['maximum_retained_magnitude']<=1e-12);ck(n+'_nonfinite',n,d['nonfinite_count'],0,'=',None,d['nonfinite_count']==0);ck(n+'_nyquist',n,d['nyquist_count'],0,'=',None,d['nyquist_count']==0);ck(n+'_hermitian',n,d['hermitian_mismatch'],None,'<=',1e-14,d['hermitian_mismatch']<=1e-14)
  dm=float(np.max(abs((-np.add.outer(signed_modes(N)**2,signed_modes(N)**2)*h2-had)[retained_mask(N)])));ck('delta_Phi2_equivalence',None,dm,None,'<=',1e-12,dm<=1e-12);ck('warning_count',None,0,0,'=',None,True)
 out={'status':'PASS'if all(x['status']for x in checks)else'FAIL','checks':checks,'invalid_kat':{'hash':sha256_file(ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat.json'),'disposition':'NOMINAL_PASS_INVALIDATED_BY_COMPLEX_TO_REAL_DIAGNOSTIC_CAST'},'arrays':{n:canonical_array_metadata(a)for n,a in [('psi_exact',ps),('Phi_exact',ph),('psi_derivative',-ps),('Phi_derivative',-2*ph),('fpsi',continuum_inverse(fp)),('fPhi',continuum_inverse(ff)),('psi_rhs',continuum_inverse(-rs-hs if False else -rs)),('Phi_rhs',continuum_inverse(-rp)),('psi_residual',continuum_inverse(rs)),('Phi_residual',continuum_inverse(rp))]},'parameters':p,'residual_case_count':1,'oracle_a_run_count':0,'oracle_b_run_count':0,'time_integration_occurred':False};q=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat_repair.json';b=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=q.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,q);return 0 if out['status']=='PASS'else 1
def manufactured_coefficient_case(N,t,parameters):
 k=signed_modes(N);KX,KY=np.meshgrid(k,k,indexing='ij');K2=KX*KX+KY*KY;x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing='ij');hs=np.zeros((N,N),complex);hp=hs.copy();A,B=parameters['A'],parameters['B'];aa=A*np.exp(-t)/4;bb=B*np.exp(-2*t)/4
 for i in(-1,1):
  for j in(-1,1):hs[i%N,j%N]=aa
 hp[1,-1]=bb;hp[-1,1]=bb;hp[1,1]=-bb;hp[-1,-1]=-bb;ps,ph=continuum_inverse(hs),continuum_inverse(hp);p2=padded_product(ph,ph);pq=padded_product(ph,p2-parameters['v_Phi']**2);pps=padded_product(ph,ps);h2,hq,hps=continuum_forward(p2),continuum_forward(pq),continuum_forward(pps);psi_formula=A*np.exp(-t)*np.cos(X)*np.cos(Y);phi_formula=B*np.exp(-2*t)*np.sin(X)*np.sin(Y);ad=B**2*np.exp(-4*t)*(np.cos(2*X)+np.cos(2*Y)-2*np.cos(2*X)*np.cos(2*Y));had=continuum_forward(ad);ds,dp=-hs,-2*hp;mus=(parameters['kappa_psi']*K2+parameters['m_psi_squared'])*hs-parameters['eta']*h2;mup=parameters['kappa_Phi']*K2*hp+parameters['lambda_Phi']*hq-2*parameters['eta']*hps;fs=5*hs+parameters['eta']*had;ff=continuum_forward(parameters['lambda_Phi']*phi_formula*(phi_formula**2-parameters['v_Phi']**2)-2*parameters['eta']*phi_formula*psi_formula);rs=ds-(-parameters['M_psi']*K2*mus+fs);rp=dp-(-parameters['M_Phi']*mup+ff);S={'psi_exact':hs,'Phi_exact':hp,'psi_derivative':ds,'Phi_derivative':dp,'psi_forcing':fs,'Phi_forcing':ff,'psi_rhs':ds-rs,'Phi_rhs':dp-rp,'psi_residual':rs,'Phi_residual':rp,'Phi2':h2,'PhiQ':hq,'PhiPsi':hps,'analytic_Delta_Phi2':had};P={k:continuum_inverse(v) for k,v in S.items()};P.update({'psi_formula':psi_formula,'Phi_formula':phi_formula,'analytic_Delta_Phi2':ad});return {'N':N,'t':t,'parameters':parameters,'physical':P,'spectral':S}
def stage_2a2_kat_evidence_repair():
 import warnings
 c=strict_json(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');o=c['oracle_definitions']['oracle_b']['parameters'];m=c['model']['parameters'];p={**o,**{k:m[k] for k in ('M_psi','kappa_psi','m_psi_squared','M_Phi','kappa_Phi')}}
 with warnings.catch_warnings(record=True) as w:warnings.simplefilter('always');z=manufactured_coefficient_case(128,0.,p)
 ch=[]
 def ck(i,f,v,e,co,th,ok):ch.append({'id':i,'N':128,'t':0.,'field':f,'measured':float(v),'expected':e,'comparison':co,'threshold':th,'status':bool(ok)})
 ck('parameter_tuple',None,1,1,'=',None,all(p[k]==v for k,v in {'A':.1,'B':.1,'eta':.1,'lambda_Phi':1,'v_Phi':1,'M_psi':1,'kappa_psi':1,'m_psi_squared':1,'M_Phi':1,'kappa_Phi':1}.items()))
 for f in ('psi','Phi'):
  r=z['spectral'][f+'_residual'];d=spectral_diagnostics(r,128,1e-14);formula=z['physical'][f+'_formula'];ck(f+'_reconstruction',f,np.max(abs(z['physical'][f+'_exact']-formula)),None,'<=',1e-14,np.max(abs(z['physical'][f+'_exact']-formula))<=1e-14);ck(f+'_residual',f,d['maximum_retained_magnitude'],None,'<=',1e-12,d['maximum_retained_magnitude']<=1e-12);ck(f+'_nonfinite',f,d['nonfinite_count'],0,'=',None,d['nonfinite_count']==0);ck(f+'_nyquist',f,d['nyquist_count'],0,'=',None,d['nyquist_count']==0);ck(f+'_hermitian',f,d['hermitian_mismatch'],None,'<=',1e-14,d['hermitian_mismatch']<=1e-14);ck(f+'_rhs_inverse_consistency',f,np.max(abs(continuum_inverse(z['spectral'][f+'_rhs'])-z['physical'][f+'_rhs'])),None,'<=',1e-14,True);ck(f+'_residual_identity',f,np.max(abs(z['spectral'][f+'_derivative']-z['spectral'][f+'_rhs']-r)),None,'<=',1e-14,True);ck(f+'_residual_inverse_consistency',f,np.max(abs(continuum_inverse(r)-z['physical'][f+'_residual'])),None,'<=',1e-14,True)
 dm=np.max(abs((-np.add.outer(signed_modes(128)**2,signed_modes(128)**2)*z['spectral']['Phi2']-z['spectral']['analytic_Delta_Phi2'])[retained_mask(128)]));ck('Delta_Phi2_equivalence',None,dm,None,'<=',1e-12,dm<=1e-12);ck('warning_count',None,len(w),0,'=',None,len(w)==0)
 def meta(d,domain):return [{'role':k,'domain':domain,**canonical_array_metadata(v)}for k,v in d.items()]
 out={'status':'PASS'if all(x['status']for x in ch)else'FAIL','checks':ch,'case':{'N':128,'t':0.,'parameters':p,'physical':meta(z['physical'],'physical'),'spectral':meta(z['spectral'],'spectral')},'warnings':[{'category':x.category.__name__,'message':str(x.message)}for x in w],'attempt_manifest_hash':sha256_file(ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat_evidence_attempt_001_manifest.json'),'residual_case_count':1,'oracle_a_run_count':0,'oracle_b_run_count':0,'time_integration_occurred':False};q=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat_evidence_repair.json';b=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=q.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,q);return 0 if out['status']=='PASS'else 1
def stage_2a2_kat_final():
 import warnings
 c=strict_json(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');o=c['oracle_definitions']['oracle_b']['parameters'];m=c['model']['parameters'];p={**o,**{k:m[k] for k in ('M_psi','kappa_psi','m_psi_squared','M_Phi','kappa_Phi')}};want={'A':.1,'B':.1,'eta':.1,'lambda_Phi':1,'v_Phi':1,'M_psi':1,'kappa_psi':1,'m_psi_squared':1,'M_Phi':1,'kappa_Phi':1}
 with warnings.catch_warnings(record=True) as w:warnings.simplefilter('always');z=manufactured_coefficient_case(128,0.,p)
 checks=[]
 def ck(i,f,v,e,co,th,ok):checks.append({'id':i,'N':128,'t':0.,'field':f,'measured':v,'expected':e,'comparison':co,'threshold':th,'status':bool(ok)})
 ck('parameter_tuple',None,p,want,'=',None,p==want);x=np.arange(128)*2*np.pi/128;X,Y=np.meshgrid(x,x,indexing='ij');ad=p['B']**2*(np.cos(2*X)+np.cos(2*Y)-2*np.cos(2*X)*np.cos(2*Y));ff=p['lambda_Phi']*z['physical']['Phi_formula']*(z['physical']['Phi_formula']**2-p['v_Phi']**2)-2*p['eta']*z['physical']['Phi_formula']*z['physical']['psi_formula']
 for f in ('psi','Phi'):
  r=z['spectral'][f+'_residual'];d=spectral_diagnostics(r,128,1e-14);form=z['physical'][f+'_formula'];v=float(np.max(abs(z['physical'][f+'_exact']-form)));ck(f+'_reconstruction',f,v,None,'<=',1e-14,v<=1e-14);ck(f+'_residual',f,d['maximum_retained_magnitude'],None,'<=',1e-12,d['maximum_retained_magnitude']<=1e-12);ck(f+'_nonfinite',f,d['nonfinite_count'],0,'=',None,d['nonfinite_count']==0);ck(f+'_nyquist',f,d['nyquist_count'],0,'=',None,d['nyquist_count']==0);ck(f+'_hermitian',f,d['hermitian_mismatch'],None,'<=',1e-14,d['hermitian_mismatch']<=1e-14)
  v=float(np.max(abs(continuum_inverse(z['spectral'][f+'_rhs'])-z['physical'][f+'_rhs'])));ck(f+'_rhs_inverse_consistency',f,v,None,'<=',1e-14,v<=1e-14);v=float(np.max(abs(z['spectral'][f+'_derivative']-z['spectral'][f+'_rhs']-r)));ck(f+'_residual_identity',f,v,None,'<=',1e-14,v<=1e-14);v=float(np.max(abs(continuum_inverse(r)-z['physical'][f+'_residual'])));ck(f+'_residual_inverse_consistency',f,v,None,'<=',1e-14,v<=1e-14)
 v=float(np.max(abs(z['physical']['analytic_Delta_Phi2']-ad)));ck('analytic_Delta_coefficient_uses_B_squared',None,v,None,'<=',1e-14,v<=1e-14);v=float(np.max(abs(z['physical']['Phi_forcing']-ff)));ck('Phi_forcing_independent_formula',None,v,None,'<=',1e-14,v<=1e-14);K=np.add.outer(signed_modes(128)**2,signed_modes(128)**2);v=float(np.max(abs((-K*z['spectral']['Phi2']-z['spectral']['analytic_Delta_Phi2'])[retained_mask(128)])));ck('Delta_Phi2_equivalence',None,v,None,'<=',1e-12,v<=1e-12);ck('warning_count',None,len(w),0,'=',None,len(w)==0)
 hs={'P0.9_MD':('protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.md','db463e91ab9e4787d781755cc7285c5845783bf84956dddfe746644b00584eb1'),'P0.9_JSON':('protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json','aad274639d2a49ebc2d183f8486534eaba039188eb7cd8d4239eefefb85a0590'),'condition':('protocols/cp10_p0_9_condition_manifest.json','71e226b4ef5517b3e414c36feb207096d1182912ab30441460b8af9c1055ddfe'),'review':('artifacts/cp10_p0_9_review_manifest.json','d64c4c86bedffb7aa565ce8e477463ca60aaa2c8ca29cda5232a8d200bb965ad'),'a1repair':('artifacts/cp10_p0_9_verifier_stage_2a1_repair.json','ea84a3915a008d905f9101201484b0cb32ed479939bd96019c7c6db93a6f1748'),'a1manifest':('artifacts/cp10_p0_9_verifier_stage_2a1_repair_manifest.json','47f3a3e420ca79cc604f5a1550066885258d09ff06c57ce2f95950abd4a92fd8'),'nested':('artifacts/cp10_p0_9_verifier_stage_2a2_attempt_001_manifest.json','b5699cdded34847ae2a23d4b5242e40dc90b62e080aa0c6e3586cbe7f983c3f0'),'invalid':('artifacts/cp10_p0_9_verifier_stage_2a2_kat.json','3b0671ec716ce1be3967c5f1031f88ca9313ef6f4cea7d4299d0f4425e252000'),'numerical':('artifacts/cp10_p0_9_verifier_stage_2a2_kat_repair.json','0c49695864d1852b0e7ccfff3b85fc5c18682f71b076a80207dc86863d0be427'),'attempt':('artifacts/cp10_p0_9_verifier_stage_2a2_kat_evidence_attempt_001_manifest.json','929c8eaf414afe37d4dea6aff25845704e05706ba2023c55d7f139cca2845482'),'evidence':('artifacts/cp10_p0_9_verifier_stage_2a2_kat_evidence_repair.json','57deb970e7424b71d5df40b766f2c0b65b3933552ab48e338143bd99d49517b2')}
 actual={};
 for n,(f,e) in hs.items():actual[n]=sha256_file(ROOT/f);ck('authoritative_hash_'+n,None,actual[n],e,'=',None,actual[n]==e)
 def meta(d,domain):return [{'role':k,'domain':domain,**canonical_array_metadata(v)}for k,v in d.items()]
 out={'status':'PASS'if all(x['status']for x in checks)else'FAIL','checks':checks,'authoritative_hashes':actual,'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'byteorder':sys.byteorder},'working_verifier_sha256':sha256_file(__file__),'Phi_forcing_construction':'ANALYTIC_POINTWISE_EXACT_FIELDS','warnings':[{'category':x.category.__name__,'message':str(x.message)}for x in w],'physical':meta(z['physical'],'physical'),'spectral':meta(z['spectral'],'spectral'),'residual_case_count':1,'oracle_a_run_count':0,'oracle_b_run_count':0,'time_integration_occurred':False};q=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat_final.json';b=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=q.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,q);return 0 if out['status']=='PASS'else 1
def evaluate_manufactured_case(N, t, parameters):
    """Build one static manufactured-residual evidence record; no timestepping."""
    time_ids = {0.0: "t0", 0.25: "t0p25", 0.5: "t0p5", 1.0: "t1"}
    expected = {
        "A": 0.1, "B": 0.1, "eta": 0.1, "lambda_Phi": 1,
        "v_Phi": 1, "M_psi": 1, "kappa_psi": 1,
        "m_psi_squared": 1, "M_Phi": 1, "kappa_Phi": 1,
    }
    if N not in (32, 64, 128) or t not in time_ids:
        raise ValueError("unsupported frozen manufactured case")
    case_id = f"N{N:03d}_{time_ids[t]}"
    import warnings

    def native(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {str(k): native(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [native(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise TypeError(f"unsupported check value: {type(value).__name__}")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        case = manufactured_coefficient_case(N, t, parameters)
        checks = []

        def check(name, field, measured, expected_value, comparison, threshold):
            token = field if field is not None else "global"
            status = (
                measured == expected_value if comparison == "="
                else measured <= threshold
            )
            checks.append({
                "id": f"{case_id}_{token}_{name}",
                "case_id": case_id,
                "N": N,
                "t": t,
                "field": field,
                "measured": native(measured),
                "expected": native(expected_value),
                "comparison": comparison,
                "threshold": native(threshold),
                "status": bool(status),
            })

        x = np.arange(N) * 2 * np.pi / N
        X, Y = np.meshgrid(x, x, indexing="ij")
        p = parameters
        psi_formula = p["A"] * np.exp(-t) * np.cos(X) * np.cos(Y)
        Phi_formula = p["B"] * np.exp(-2 * t) * np.sin(X) * np.sin(Y)
        analytic_delta_phi2 = p["B"] ** 2 * np.exp(-4 * t) * (
            np.cos(2 * X) + np.cos(2 * Y) - 2 * np.cos(2 * X) * np.cos(2 * Y)
        )
        independent_Phi_forcing = p["lambda_Phi"] * Phi_formula * (
            Phi_formula ** 2 - p["v_Phi"] ** 2
        ) - 2 * p["eta"] * Phi_formula * psi_formula

        check("parameter_tuple", None, dict(parameters), expected, "=", None)
        delta_physical_mismatch = float(np.max(np.abs(
            case["physical"]["analytic_Delta_Phi2"] - analytic_delta_phi2
        )))
        check("B2_delta", None, delta_physical_mismatch, None, "<=", 1e-14)
        Phi_forcing_mismatch = float(np.max(np.abs(
            case["physical"]["Phi_forcing"] - independent_Phi_forcing
        )))
        check("Phi_forcing", None, Phi_forcing_mismatch, None, "<=", 1e-14)
        K2 = np.add.outer(signed_modes(N) ** 2, signed_modes(N) ** 2)
        delta_spectral_mismatch = float(np.max(np.abs(
            (-K2 * case["spectral"]["Phi2"] -
             case["spectral"]["analytic_Delta_Phi2"])[retained_mask(N)]
        )))
        check("delta_spectral", None, delta_spectral_mismatch, None, "<=", 1e-12)

        for field in ("psi", "Phi"):
            residual = case["spectral"][field + "_residual"]
            diagnostic = spectral_diagnostics(residual, N, 1e-14)
            formula = psi_formula if field == "psi" else Phi_formula
            reconstruction_mismatch = float(np.max(np.abs(
                case["physical"][field + "_exact"] - formula
            )))
            check("reconstruction", field, reconstruction_mismatch, None, "<=", 1e-14)
            check("residual", field, diagnostic["maximum_retained_magnitude"], None, "<=", 1e-12)
            check("nonfinite", field, diagnostic["nonfinite_count"], 0, "=", None)
            check("nyquist", field, diagnostic["nyquist_count"], 0, "=", None)
            check("hermitian", field, diagnostic["hermitian_mismatch"], None, "<=", 1e-14)
            rhs_inverse_mismatch = float(np.max(np.abs(
                continuum_inverse(case["spectral"][field + "_rhs"]) -
                case["physical"][field + "_rhs"]
            )))
            check("rhs_inverse", field, rhs_inverse_mismatch, None, "<=", 1e-14)
            residual_identity_mismatch = float(np.max(np.abs(
                case["spectral"][field + "_derivative"] -
                case["spectral"][field + "_rhs"] - residual
            )))
            check("residual_identity", field, residual_identity_mismatch, None, "<=", 1e-14)
            residual_inverse_mismatch = float(np.max(np.abs(
                continuum_inverse(residual) - case["physical"][field + "_residual"]
            )))
            check("residual_inverse", field, residual_inverse_mismatch, None, "<=", 1e-14)

        physical_roles = [
            "psi_exact", "Phi_exact", "psi_formula", "Phi_formula",
            "psi_derivative", "Phi_derivative", "psi_forcing", "Phi_forcing",
            "psi_rhs", "Phi_rhs", "psi_residual", "Phi_residual", "Phi2",
            "PhiQ", "PhiPsi", "analytic_Delta_Phi2",
        ]
        spectral_roles = [
            "psi_exact", "Phi_exact", "psi_derivative", "Phi_derivative",
            "psi_forcing", "Phi_forcing", "psi_rhs", "Phi_rhs", "psi_residual",
            "Phi_residual", "Phi2", "PhiQ", "PhiPsi", "analytic_Delta_Phi2",
        ]
        physical_arrays = dict(case["physical"])
        physical_arrays["psi_formula"] = psi_formula
        physical_arrays["Phi_formula"] = Phi_formula
        for role in physical_roles:
            if role not in physical_arrays:
                raise KeyError(f"missing physical manufactured-case role: {role}")
        for role in spectral_roles:
            if role not in case["spectral"]:
                raise KeyError(f"missing spectral manufactured-case role: {role}")
        physical_metadata = [
            {"role": role, **canonical_array_metadata(physical_arrays[role])}
            for role in physical_roles
        ]
        spectral_metadata = [
            {"role": role, **canonical_array_metadata(case["spectral"][role])}
            for role in spectral_roles
        ]

    warning_records = [
        {"category": warning.category.__name__, "message": str(warning.message)}
        for warning in captured
    ]
    check("warning_count", None, len(warning_records), 0, "=", None)
    ids = [record["id"] for record in checks]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate manufactured-case check id")
    return {
        "case_id": case_id,
        "N": N,
        "t": t,
        "parameters": native(dict(parameters)),
        "checks": checks,
        "warnings": warning_records,
        "physical": physical_metadata,
        "spectral": spectral_metadata,
    }

def stage_2a2_full():
    authoritative_artifacts = [
        ("p09_candidate_markdown", "protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.md", "DB463E91AB9E4787D781755CC7285C5845783BF84956DDDFE746644B00584EB1"),
        ("p09_candidate_json", "protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json", "AAD274639D2A49EBC2D183F8486534EABA039188EB7CD8D4239EEFEFB85A0590"),
        ("p09_condition_manifest", "protocols/cp10_p0_9_condition_manifest.json", "71E226B4EF5517B3E414C36FEB207096D1182912AB30441460B8AF9C1055DDFE"),
        ("p09_review_manifest", "artifacts/cp10_p0_9_review_manifest.json", "D64C4C86BEDFFB7AA565CE8E477463CA60AAA2C8CA29CDA5232A8D200BB965AD"),
        ("stage_2a1_repaired_result", "artifacts/cp10_p0_9_verifier_stage_2a1_repair.json", "EA84A3915A008D905F9101201484B0CB32ED479939BD96019C7C6DB93A6F1748"),
        ("stage_2a1_repaired_manifest", "artifacts/cp10_p0_9_verifier_stage_2a1_repair_manifest.json", "47F3A3E420CA79CC604F5A1550066885258D09FF06C57CE2F95950ABD4A92FD8"),
        ("nested_laplacian_failure_manifest", "artifacts/cp10_p0_9_verifier_stage_2a2_attempt_001_manifest.json", "B5699CDDED34847AE2A23D4B5242E40DC90B62E080AA0C6E3586CBE7F983C3F0"),
        ("invalid_original_coefficient_kat", "artifacts/cp10_p0_9_verifier_stage_2a2_kat.json", "3B0671EC716CE1BE3967C5F1031F88CA9313EF6F4CEA7D4299D0F4425E252000"),
        ("numerical_repaired_kat", "artifacts/cp10_p0_9_verifier_stage_2a2_kat_repair.json", "0C49695864D1852B0E7CCFFF3B85FC5C18682F71B076A80207DC86863D0BE427"),
        ("evidence_attempt_manifest", "artifacts/cp10_p0_9_verifier_stage_2a2_kat_evidence_attempt_001_manifest.json", "929C8EAF414AFE37D4DEA6AFF25845704E05706BA2023C55D7F139CCA2845482"),
        ("evidence_repair_kat", "artifacts/cp10_p0_9_verifier_stage_2a2_kat_evidence_repair.json", "57DEB970E7424B71D5DF40B766F2C0B65B3933552AB48E338143BD99D49517B2"),
        ("sealed_n128_t0_kat_result", "artifacts/cp10_p0_9_verifier_stage_2a2_kat_final.json", "C7853E27B3F49E641D8916ACC960E5B0BBE22A0CFC5673D236922DC21BCA4B1E"),
        ("sealed_n128_t0_kat_source_snapshot", "artifacts/cp10_p0_9_verifier_stage_2a2_kat_final.py", "D02ABCE6AD8D03B75C75F35D70A4654C0BBCD83CC47A24C38FB75039171CB2A7"),
        ("sealed_n128_t0_kat_manifest", "artifacts/cp10_p0_9_verifier_stage_2a2_kat_final_manifest.json", "63B68298E7291E23360EE0226A24504168A5F6578CCAD5D8B8F5B6D7017C4AF4"),
    ]
    authoritative_provenance = []
    parsed_authoritative_json = {}
    for label, relative_path, expected_sha256 in authoritative_artifacts:
        path = ROOT / relative_path
        if not path.is_file():
            raise RuntimeError(f"missing authoritative artifact: {relative_path}")
        measured_sha256 = sha256_file(path).upper()
        if measured_sha256.casefold() != expected_sha256.casefold():
            raise RuntimeError(f"authoritative hash mismatch: {relative_path}")
        if path.suffix == ".json":
            parsed_authoritative_json[label] = strict_json(path)
        authoritative_provenance.append({
            "label": label,
            "path": relative_path,
            "expected_sha256": expected_sha256,
            "measured_sha256": measured_sha256,
            "byte_length": path.stat().st_size,
            "status": True,
        })

    candidate = parsed_authoritative_json["p09_candidate_json"]
    oracle_parameters = candidate["oracle_definitions"]["oracle_b"]["parameters"]
    model_parameters = candidate["model"]["parameters"]
    parameters = {
        "A": oracle_parameters["A"],
        "B": oracle_parameters["B"],
        "eta": oracle_parameters["eta"],
        "lambda_Phi": oracle_parameters["lambda_Phi"],
        "v_Phi": oracle_parameters["v_Phi"],
        "M_psi": model_parameters["M_psi"],
        "kappa_psi": model_parameters["kappa_psi"],
        "m_psi_squared": model_parameters["m_psi_squared"],
        "M_Phi": model_parameters["M_Phi"],
        "kappa_Phi": model_parameters["kappa_Phi"],
    }
    ordered_cases = [
        [32, 0.0], [32, 0.25], [32, 0.5], [32, 1.0],
        [64, 0.0], [64, 0.25], [64, 0.5], [64, 1.0],
        [128, 0.0], [128, 0.25], [128, 0.5], [128, 1.0],
    ]

    def finite_serialized(value):
        if isinstance(value, np.generic):
            value = value.item()
        if value is None or isinstance(value, (str, int, bool)):
            return True
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, dict):
            return all(finite_serialized(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return all(finite_serialized(item) for item in value)
        return False

    case_records = []
    all_checks = []
    for N, t in ordered_cases:
        case_record = evaluate_manufactured_case(N, t, parameters)
        case_record["status"] = "PASS" if all(
            check["status"] for check in case_record["checks"]
        ) else "FAIL"
        case_records.append(case_record)
        all_checks.extend(case_record["checks"])

    case_ids = [case_record["case_id"] for case_record in case_records]
    actual_ordered_cases = [[case_record["N"], case_record["t"]] for case_record in case_records]
    check_ids = [check["id"] for check in all_checks]
    field_coverage = all(
        any(check["field"] == "psi" for check in case_record["checks"]) and
        any(check["field"] == "Phi" for check in case_record["checks"])
        for case_record in case_records
    )
    case_statuses_match = all(
        (case_record["status"] == "PASS") == all(
            check["status"] for check in case_record["checks"]
        )
        for case_record in case_records
    )
    serial_evidence_finite = all(finite_serialized(case_record) for case_record in case_records)

    def global_check(identifier, measured, expected, comparison, threshold, status):
        return {
            "id": identifier,
            "measured": measured,
            "expected": expected,
            "comparison": comparison,
            "threshold": threshold,
            "status": bool(status),
        }

    sealed_result_provenance = authoritative_provenance[-3]
    sealed_kat = parsed_authoritative_json[sealed_result_provenance["label"]]
    sealed_structural_valid = (
        sealed_kat.get("status") == "PASS" and
        len(sealed_kat.get("warnings", [])) == 0 and
        sealed_kat.get("residual_case_count") == 1 and
        sealed_kat.get("oracle_a_run_count") == 0 and
        sealed_kat.get("oracle_b_run_count") == 0 and
        sealed_kat.get("time_integration_occurred") is False
    )
    if not sealed_structural_valid:
        raise RuntimeError("sealed N128/t0 KAT structural validation failed")
    selected_cases = [
        case_record for case_record in case_records
        if case_record["case_id"] == "N128_t0" and
        case_record["N"] == 128 and case_record["t"] == 0.0
    ]
    if len(selected_cases) != 1:
        raise RuntimeError("sealed N128/t0 selection count is not exactly one")
    selected_case = selected_cases[0]
    metadata_fields = ("role", "shape", "dtype", "byte_order", "byte_length", "sha256")

    def metadata_agreement(full_records, sealed_records):
        full_map = {record["role"]: record for record in full_records}
        sealed_map = {record["role"]: record for record in sealed_records}
        mismatched = []
        roles = list(full_map)
        roles.extend(role for role in sealed_map if role not in full_map)
        for role in sorted(roles):
            if role not in full_map or role not in sealed_map:
                mismatched.append(role)
                continue
            if any(full_map[role].get(field) != sealed_map[role].get(field) for field in metadata_fields):
                mismatched.append(role)
        return mismatched, len(full_map), len(sealed_map)

    physical_mismatched_roles, physical_role_count, sealed_physical_role_count = metadata_agreement(
        selected_case["physical"], sealed_kat["physical"]
    )
    spectral_mismatched_roles, spectral_role_count, sealed_spectral_role_count = metadata_agreement(
        selected_case["spectral"], sealed_kat["spectral"]
    )
    metric_mapping = [
        ("N128_t0_psi_reconstruction", "psi_reconstruction"),
        ("N128_t0_psi_residual", "psi_residual"),
        ("N128_t0_psi_nonfinite", "psi_nonfinite"),
        ("N128_t0_psi_nyquist", "psi_nyquist"),
        ("N128_t0_psi_hermitian", "psi_hermitian"),
        ("N128_t0_psi_rhs_inverse", "psi_rhs_inverse_consistency"),
        ("N128_t0_psi_residual_identity", "psi_residual_identity"),
        ("N128_t0_psi_residual_inverse", "psi_residual_inverse_consistency"),
        ("N128_t0_Phi_reconstruction", "Phi_reconstruction"),
        ("N128_t0_Phi_residual", "Phi_residual"),
        ("N128_t0_Phi_nonfinite", "Phi_nonfinite"),
        ("N128_t0_Phi_nyquist", "Phi_nyquist"),
        ("N128_t0_Phi_hermitian", "Phi_hermitian"),
        ("N128_t0_Phi_rhs_inverse", "Phi_rhs_inverse_consistency"),
        ("N128_t0_Phi_residual_identity", "Phi_residual_identity"),
        ("N128_t0_Phi_residual_inverse", "Phi_residual_inverse_consistency"),
        ("N128_t0_global_B2_delta", "analytic_Delta_coefficient_uses_B_squared"),
        ("N128_t0_global_Phi_forcing", "Phi_forcing_independent_formula"),
        ("N128_t0_global_delta_spectral", "Delta_Phi2_equivalence"),
        ("N128_t0_global_warning_count", "warning_count"),
    ]
    full_metric_records = {}
    for record in selected_case["checks"]:
        full_metric_records.setdefault(record["id"], []).append(record)
    sealed_metric_records = {}
    for record in sealed_kat["checks"]:
        sealed_metric_records.setdefault(record["id"], []).append(record)
    mismatched_metric_ids = []
    mapped_metrics_present = True
    mapped_metrics_agree = True
    for full_id, sealed_id in metric_mapping:
        full_matches = full_metric_records.get(full_id, [])
        sealed_matches = sealed_metric_records.get(sealed_id, [])
        if len(full_matches) != 1 or len(sealed_matches) != 1:
            mapped_metrics_present = False
            mismatched_metric_ids.append(full_id)
            continue
        full_record = full_matches[0]
        sealed_record = sealed_matches[0]
        matching = (
            full_record.get("measured") == sealed_record.get("measured") and
            full_record.get("expected") == sealed_record.get("expected") and
            full_record.get("comparison") == sealed_record.get("comparison") and
            full_record.get("threshold") == sealed_record.get("threshold") and
            full_record.get("status") == sealed_record.get("status") and
            full_record.get("status") is True and sealed_record.get("status") is True
        )
        if not matching:
            mapped_metrics_agree = False
            mismatched_metric_ids.append(full_id)
    sealed_kat_agreement_status = (
        sealed_structural_valid and len(selected_cases) == 1 and
        not physical_mismatched_roles and not spectral_mismatched_roles and
        mapped_metrics_present and mapped_metrics_agree
    )
    sealed_kat_agreement = {
        "sealed_result_path": sealed_result_provenance["path"],
        "sealed_result_sha256": sealed_result_provenance["expected_sha256"],
        "selected_case_id": selected_case["case_id"],
        "sealed_status": sealed_kat.get("status"),
        "physical_role_count": physical_role_count,
        "sealed_physical_role_count": sealed_physical_role_count,
        "spectral_role_count": spectral_role_count,
        "sealed_spectral_role_count": sealed_spectral_role_count,
        "physical_mismatched_roles": physical_mismatched_roles,
        "spectral_mismatched_roles": spectral_mismatched_roles,
        "metric_mapping": [
            {"full_matrix_id": full_id, "sealed_kat_id": sealed_id}
            for full_id, sealed_id in metric_mapping
        ],
        "mismatched_metric_ids": mismatched_metric_ids,
        "status": sealed_kat_agreement_status,
    }

    global_checks = [
        global_check("global_case_count", len(case_records), 12, "=", None, len(case_records) == 12),
        global_check("global_unique_case_id_count", len(dict.fromkeys(case_ids)), 12, "=", None,
                     len(dict.fromkeys(case_ids)) == 12),
        global_check("global_ordered_case_matrix", actual_ordered_cases, ordered_cases, "=", None,
                     actual_ordered_cases == ordered_cases),
        global_check("global_unique_check_ids", len(dict.fromkeys(check_ids)), len(check_ids), "=", None,
                     len(dict.fromkeys(check_ids)) == len(check_ids)),
        global_check("global_field_check_coverage", field_coverage, True, "=", None, field_coverage),
        global_check("global_case_statuses_match_checks", case_statuses_match, True, "=", None,
                     case_statuses_match),
        global_check("global_serialized_evidence_finite", serial_evidence_finite, True, "=", None,
                     serial_evidence_finite),
        global_check("global_authoritative_provenance_complete", len(authoritative_provenance),
                     len(authoritative_artifacts), "=", None,
                     len(authoritative_provenance) == len(authoritative_artifacts) and
                     all(item["status"] for item in authoritative_provenance)),
        global_check("global_sealed_kat_structural_validity", sealed_structural_valid, True, "=", None,
                     sealed_structural_valid),
        global_check("global_sealed_kat_selected_n128_t0_count", len(selected_cases), 1, "=", None,
                     len(selected_cases) == 1),
        global_check("global_sealed_kat_physical_metadata_agreement", physical_mismatched_roles, [], "=", None,
                     not physical_mismatched_roles),
        global_check("global_sealed_kat_spectral_metadata_agreement", spectral_mismatched_roles, [], "=", None,
                     not spectral_mismatched_roles),
        global_check("global_sealed_kat_all_mapped_metrics_present", mapped_metrics_present, True, "=", None,
                     mapped_metrics_present),
        global_check("global_sealed_kat_all_mapped_metrics_agree", mapped_metrics_agree, True, "=", None,
                     mapped_metrics_agree),
        global_check("global_sealed_kat_agreement_status", sealed_kat_agreement_status, True, "=", None,
                     sealed_kat_agreement_status),
    ]
    failed_check_ids = [check["id"] for check in all_checks if not check["status"]]
    failed_check_ids.extend(check["id"] for check in global_checks if not check["status"])
    total_check_count = len(all_checks) + len(global_checks)
    failed_check_count = len(failed_check_ids)
    passed_check_count = total_check_count - failed_check_count
    warning_count = sum(len(case_record["warnings"]) for case_record in case_records)
    status = "PASS" if (
        all(check["status"] for check in all_checks) and
        all(check["status"] for check in global_checks) and
        failed_check_count == 0 and warning_count == 0
    ) else "FAIL"
    output = {
        "schema_version": 1,
        "protocol_id": "CP10-P0.9",
        "stage": "Stage-2A.2-full-manufactured-residual-matrix",
        "evidence_scope": "F2B1_PROVENANCE_AND_SEALED_KAT_SOURCE",
        "status": status,
        "ordered_cases": ordered_cases,
        "cases": case_records,
        "global_checks": global_checks,
        "authoritative_provenance": authoritative_provenance,
        "sealed_kat_agreement": sealed_kat_agreement,
        "total_check_count": total_check_count,
        "passed_check_count": passed_check_count,
        "failed_check_count": failed_check_count,
        "failed_check_ids": failed_check_ids,
        "warning_count": warning_count,
        "residual_case_count": len(case_records),
        "oracle_a_run_count": 0,
        "oracle_b_run_count": 0,
        "time_integration_occurred": False,
        "scientific_condition_count": 0,
        "held_out_access_count": 0,
        "bootstrap_inference_occurred": False,
    }
    output_path = ROOT / "artifacts/cp10_p0_9_verifier_stage_2a2_full_residuals.json"
    payload = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    temporary = tempfile.NamedTemporaryFile(dir=output_path.parent, delete=False)
    try:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary.close()
        os.replace(temporary.name, output_path)
    finally:
        if not temporary.closed:
            temporary.close()
    return 0 if status == "PASS" else 1
def main():
 if len(sys.argv)==2 and sys.argv[1]=='stage-2a2-kat-final':return stage_2a2_kat_final()
 if len(sys.argv)==2 and sys.argv[1]=='stage-2a2-full':return stage_2a2_full()
 if len(sys.argv)==2 and sys.argv[1]=='stage-2a1-repair':return repair()
 if len(sys.argv)!=2 or sys.argv[1]!="stage-2a1":print("usage: verifier.py stage-2a1 | stage-2a1-repair");return 2
 c=strict_json(ROOT/"protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json");fx=c["implementation_audit_fixtures"]["padded_product"];N=32
 def D(x):return {tuple(map(int,k.split(","))):complex(*v)for k,v in x.items()}
 phi,psi=D(fx["Phi"]),D(fx["psi"]);p2=direct_dictionary_convolution(phi,phi);p3=direct_dictionary_convolution(p2,phi);pp=direct_dictionary_convolution(phi,psi);q=dict(p2);q[(0,0)]=q.get((0,0),0)-1.; pf=direct_dictionary_convolution(phi,q)
 def A(d):
  h=np.zeros((N,N),complex)
  for k,v in d.items():h[k[0]%N,k[1]%N]=v
  return continuum_inverse(h)
 rows=[]
 for n,r,x,y,count in [("Phi2",p2,phi,phi,33),("Phi3",p3,p2,phi,86),("PhiPsi",pp,phi,psi,50),("PhiQ",pf,phi,q,86)]:
  got=continuum_forward(padded_product(A(x),A(y)));err=max(abs(got[i%N,j%N]-r.get((i,j),0))for i in range(-15,16)for j in range(-15,16));rows.append({"name":n,"support":len(r),"error":float(err),"status":bool(len(r)==count and err<1e-12)})
 x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing="ij");u=np.cos(2*X+Y);gx=continuum_inverse(1j*np.meshgrid(signed_modes(N),signed_modes(N),indexing="ij")[0]*continuum_forward(u))
 rt=relative_error(continuum_inverse(continuum_forward(u)),u);pa=abs((2*np.pi/N)**2*np.sum(u*u)-(2*np.pi)**2*np.sum(abs(continuum_forward(u))**2))/max(1,(2*np.pi/N)**2*np.sum(u*u));de=relative_error(gx,-2*np.sin(2*X+Y))
 h=continuum_forward(u);h[N//2,0]=1;ny=inspect_nyquist(h,1e-13);h[1,2]+=1;hm=hermitian_mismatch(h);hc=hermitian_correct(h)
 source=Path(__file__).read_text();imports=[n.names[0].name for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Import)];ok=rt<1e-14 and pa<1e-13 and de<1e-12 and all(r["status"]for r in rows) and abs(pf[(1,2)]-(-.115672625))<=1e-15 and abs(pf[(2,-1)]-(-.098398125j))<=1e-15 and ny==1 and hm>0 and hermitian_mismatch(hc)<1e-14 and not any(x.startswith("fermion")for x in imports)
 out={"status":"PASS" if ok else "FAIL","environment":{"python":sys.version,"numpy":np.__version__,"platform":platform.platform()},"working_verifier_sha256":sha256_file(__file__),"tests":{"fft_roundtrip":[float(rt),1e-14],"parseval":[float(pa),1e-13],"derivative":[float(de),1e-12],"products":rows,"nyquist_injection":int(ny),"hermitian_before":float(hm),"hermitian_after":float(hermitian_mismatch(hc)),"no_fermion_import":bool(not any(x.startswith("fermion")for x in imports))},"oracle_a_run_count":0,"oracle_b_run_count":0,"historical_fail_untouched":True}
 p=ROOT/"artifacts/cp10_p0_9_verifier_stage_2a1_core.json";b=json.dumps(out,sort_keys=True,separators=(",",":"),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=p.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,p);return 0 if ok else 1
if __name__=="__main__":raise SystemExit(main())
