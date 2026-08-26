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
 a=np.asarray(field,dtype=np.float64); return np.fft.fft2(a)/a.size
def continuum_inverse(spectrum):
 a=np.asarray(spectrum,dtype=np.complex128); return np.fft.ifft2(a*a.size).real
def count_nonfinite(*arrays): return int(sum(np.size(a)-np.count_nonzero(np.isfinite(a)) for a in arrays))
def signed_modes(N): return np.fft.fftfreq(N,1/N).astype(int)
def retained_mask(N):
 k=signed_modes(N);a,b=np.meshgrid(k,k,indexing="ij");return (abs(a)<=N//2-1)&(abs(b)<=N//2-1)
def inspect_nyquist(spectrum,tolerance=0.):
 N=spectrum.shape[0]; return int(np.count_nonzero(abs(spectrum[N//2,:])>tolerance)+np.count_nonzero(abs(spectrum[:,N//2])>tolerance)-int(abs(spectrum[N//2,N//2])>tolerance))
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
def manufactured_coefficient_case(N,t,parameters):
 k=signed_modes(N);KX,KY=np.meshgrid(k,k,indexing='ij');K2=KX*KX+KY*KY;x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing='ij');hs=np.zeros((N,N),complex);hp=hs.copy();aa=parameters['A']*np.exp(-t)/4;bb=parameters['B']*np.exp(-2*t)/4
 for i in(-1,1):
  for j in(-1,1):hs[i%N,j%N]=aa
 hp[1,-1]=bb;hp[-1,1]=bb;hp[1,1]=-bb;hp[-1,-1]=-bb;ps,ph=continuum_inverse(hs),continuum_inverse(hp);aps=.1*np.exp(-t)*np.cos(X)*np.cos(Y);aph=.1*np.exp(-2*t)*np.sin(X)*np.sin(Y);p2=padded_product(ph,ph);pq=padded_product(ph,p2-parameters['v_Phi']**2);pps=padded_product(ph,ps);h2,hq,hps=continuum_forward(p2),continuum_forward(pq),continuum_forward(pps);ad=.01*np.exp(-4*t)*(np.cos(2*X)+np.cos(2*Y)-2*np.cos(2*X)*np.cos(2*Y));had=continuum_forward(ad);mu_s=(K2+1)*hs-parameters['eta']*h2;mu_p=K2*hp+parameters['lambda_Phi']*hq-2*parameters['eta']*hps;fp=5*hs+parameters['eta']*had;ff=continuum_forward(parameters['lambda_Phi']*aph*(aph*aph-parameters['v_Phi']**2)-2*parameters['eta']*aph*aps);rs=-hs-(-K2*mu_s+fp);rp=-2*hp-(-mu_p+ff);return ps,ph,aps,aph,h2,had,rs,rp,fp,ff
def stage_2a2_kat():
 c=strict_json(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');p=c['oracle_definitions']['oracle_b']['parameters'];N=128;t=0.;ps,ph,aps,aph,h2,had,rs,rp,fp,ff=manufactured_coefficient_case(N,t,p);checks=[]
 def ck(i,field,val,exp,cmp,th,ok):checks.append({'id':i,'N':N,'t':t,'field':field,'measured':float(val),'expected':exp,'comparison':cmp,'threshold':th,'status':bool(ok)})
 for name,a,b,r in [('psi',ps,aps,rs),('Phi',ph,aph,rp)]:
  re=float(np.max(abs(a-b)));mx=float(np.max(abs(continuum_forward(r)[retained_mask(N)])));nf=count_nonfinite(r);ny=inspect_nyquist(continuum_forward(r),1e-14);hm=hermitian_mismatch(continuum_forward(r));ck('reconstruction',name,re,None,'<=',1e-14,re<=1e-14);ck('residual',name,mx,None,'<=',1e-12,mx<=1e-12);ck('nonfinite',name,nf,0,'=',None,nf==0);ck('nyquist',name,ny,0,'=',None,ny==0);ck('hermitian',name,hm,None,'<=',1e-14,hm<=1e-14)
 dm=float(np.max(abs((-np.add.outer(signed_modes(N)**2,signed_modes(N)**2)*h2-had)[retained_mask(N)])));ck('delta_phi2',None,dm,None,'<=',1e-12,dm<=1e-12)
 out={'status':'PASS'if all(z['status']for z in checks)else'FAIL','checks':checks,'input_hashes':c['revision_provenance']['p0_8_authoritative_hashes'],'failed_path_manifest_sha256':sha256_file(ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_attempt_001_manifest.json'),'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'byteorder':sys.byteorder},'parameters':p,'arrays':{n:canonical_array_metadata(a)for n,a in [('psi_exact',ps),('Phi_exact',ph),('fpsi',continuum_inverse(fp)),('fPhi',continuum_inverse(ff)),('psi_residual',continuum_inverse(rs)),('Phi_residual',continuum_inverse(rp))]},'residual_case_count':1,'oracle_a_run_count':0,'oracle_b_run_count':0,'time_integration_occurred':False};q=ROOT/'artifacts/cp10_p0_9_verifier_stage_2a2_kat.json';b=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=q.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,q);return 0 if out['status']=='PASS'else 1
def main():
 if len(sys.argv)==2 and sys.argv[1]=='stage-2a2-kat':return stage_2a2_kat()
 if len(sys.argv)==2 and sys.argv[1]=='stage-2a2':return stage_2a2()
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
