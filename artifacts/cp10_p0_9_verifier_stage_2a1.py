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
def continuum_forward(field): return np.fft.fft2(np.asarray(field,dtype=np.float64))/field.size
def continuum_inverse(spectrum): return np.fft.ifft2(np.asarray(spectrum,dtype=np.complex128)*spectrum.size).real
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
 return {"shape":list(a.shape),"dtype":str(a.dtype),"byte_order":"little","byte_length":a.nbytes,"sha256":hashlib.sha256(a.tobytes()).hexdigest()}
def main():
 if len(sys.argv)!=2 or sys.argv[1]!="stage-2a1":print("usage: verifier.py stage-2a1");return 2
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
