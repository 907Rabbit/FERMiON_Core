from __future__ import annotations
import hashlib,json,math,os,tempfile
from dataclasses import dataclass
from pathlib import Path
import numpy as np
P8={"protocols/cp10_p0_8_IMPLEMENTATION_FREEZE_CANDIDATE.md":"81E5DFE778C2021594F51CD80FDFD3CEBA9B5B66494B095CCAC713DCA37EEB55","protocols/cp10_p0_8_IMPLEMENTATION_FREEZE_CANDIDATE.json":"1632F51CA83ECA26C966C236F8D61D296AAC10332129C77A3A9D04A2463DB782","protocols/cp10_p0_8_condition_manifest.json":"7088A06E6C78B6BEBD671EDAE7739AC191F1B5386CC1F4C6BC100BEE27DB89CB","artifacts/cp10_p0_8_review_manifest.json":"3B73AD048D1CA1870DAC150F21FACF9CBD75D1C48175AA2B8740C1FC71BDADE7","artifacts/cp10_p0_8_fixture_verification.json":"424E7D9079687DAF4527456770CD6E1E3AE8A6D9D26E6D91EB4D2C7E157ADA9E","protocols/cp10_p0_8_FREEZE_RECEIPT.json":"1F5C60C7673B23F47C700254000963B60C4D2A1381797D871447B4313F55AE95","artifacts/cp10_p0_8_FREEZE_RECEIPT.json.sha256":"F0B275C1E8429EAEBD16D44CF53BFC3D82ADE7CC83772E733F9F4D84B2B01ABD","artifacts/cp10_p0_7_bootstrap_indices.bin":"A896E1707AA36A36FC6C0048E74A8D4546890C9CD6B78E5479D6F57028BE4654","artifacts/cp10_p0_7_bootstrap_indices_manifest.json":"2879DCDE2E58161ACE411E1EE2AB496276BFF1730DE634854BA071F3386B917A"}
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def strict(path):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d: raise ValueError("duplicate JSON key: "+k)
   d[k]=v
  return d
 def constant(x): raise ValueError("nonfinite JSON constant: "+x)
 return json.loads(Path(path).read_bytes().decode("utf-8","strict"),object_pairs_hook=pairs,parse_constant=constant)
@dataclass(frozen=True)
class FrozenProtocol: root:Path; config:dict; conditions:dict; receipt:dict; bootstrap:bytes
def verify_frozen_bundle(root="."):
 root=Path(root).resolve()
 for p,h in P8.items():
  if sha(root/p).upper()!=h: raise RuntimeError("frozen hash mismatch: "+p)
 c=strict(root/"protocols/cp10_p0_8_IMPLEMENTATION_FREEZE_CANDIDATE.json");m=strict(root/"protocols/cp10_p0_8_condition_manifest.json");r=strict(root/"protocols/cp10_p0_8_FREEZE_RECEIPT.json");f=strict(root/"artifacts/cp10_p0_8_fixture_verification.json")
 if f["overall_status"]!="PASS" or r["protocol_status"]!="FROZEN": raise RuntimeError("unfrozen bundle")
 if (root/"artifacts/cp10_p0_8_FREEZE_RECEIPT.json.sha256").read_text().strip()!=sha(root/"protocols/cp10_p0_8_FREEZE_RECEIPT.json")+"  protocols/cp10_p0_8_FREEZE_RECEIPT.json": raise RuntimeError("receipt checksum")
 rec=m["records"]; co=[x for x in rec if x["record_type"]=="condition"];re=[x for x in rec if x["record_type"]=="replay_attempt"]
 if {s:sum(x["stage"]==s for x in co) for s in "BCDE"}!={"B":24,"C":120,"D":32,"E":48} or len(co)!=224 or len(re)!=9 or len({x["condition_id"] for x in rec})!=233: raise RuntimeError("condition set")
 if m["calibration_seeds"]!=list(range(1,9)) or m["held_out_seeds"]!=list(range(1001,1017)) or any(x["seed"]==0 for x in rec): raise RuntimeError("seed domain")
 b=(root/"artifacts/cp10_p0_7_bootstrap_indices.bin").read_bytes()
 if len(b)!=160000 or b[:16].hex()!="060b040603050a0906090605000e0601" or b[-16:].hex()!="0201080e030f020a0f0c0e090005060d": raise RuntimeError("bootstrap")
 return FrozenProtocol(root,c,m,r,b)
MASK=0xffffffff;M0=0xD2511F53;M1=0xCD9E8D57;W0=0x9E3779B9;W1=0xBB67AE85
def philox(counter,key):
 c0,c1,c2,c3=(x&MASK for x in counter);k0,k1=(x&MASK for x in key)
 for _ in range(10):
  # Random123 Philox4x32 round: the M1 product feeds c0/c1 and
  # the M0 product feeds c2/c3 (not the other way around).
  c0,c1,c2,c3=((M1*c2>>32)^c1^k0,(M1*c2)&MASK,(M0*c0>>32)^c3^k1,(M0*c0)&MASK);k0=(k0+W0)&MASK;k1=(k1+W1)&MASK
 return c0,c1,c2,c3
def zigzag32(k):
 if not -2**31<=k<2**31:raise ValueError("mode int32")
 return (2*k if k>=0 else -2*k-1)&MASK
def frozen_kats(): return {"zero":philox((0,0,0,0),(0,0)),"psi":philox((2,0,0,0x494E4954),(0,0x50534931)),"phi":philox((0,2,0,0x494E4954),(0,0x50484931)),"bootstrap":philox((0,0,0,0x42535450),(0x013527D9,0x42535446))}
def modal_initializer(seed,field_tag,N):
 """Frozen representative-mode Philox initializer, reusable at every grid."""
 h=np.zeros((N,N),np.complex128)
 for ky in range(-4,5):
  for kx in range(-4,5):
   if not (ky>0 or (ky==0 and kx>0)) or not (0 < math.hypot(kx,ky) <= 4): continue
   r0,r1,*_=philox((zigzag32(kx),zigzag32(ky),0,0x494E4954),(seed&MASK,((seed>>32)&MASK)^field_tag))
   u1=(r0+.5)/2**32;u2=(r1+.5)/2**32;g1=math.sqrt(-2*math.log(u1))*math.cos(2*math.pi*u2);g2=math.sqrt(-2*math.log(u1))*math.sin(2*math.pi*u2);z=(g1+1j*g2)/math.sqrt(2)
   h[kx%N,ky%N]=z;h[-kx%N,-ky%N]=z.conjugate()
 rms=math.sqrt(np.sum(abs(h)**2))
 if rms==0: raise RuntimeError("empty modal initializer")
 return h*(.05/rms)
class SeedAccess:
 def __init__(self,log): self.log=Path(log);self.events=[]
 def request(self,seed,authorized=False,requesting_component="unknown"):
  held=1001<=int(seed)<=1016; granted=(not held) or bool(authorized)
  self.events.append({"sequence":len(self.events)+1,"seed":int(seed),"is_held_out":held,"authorization_present":bool(authorized),"granted":granted,"requesting_component":requesting_component})
  # Persist the denial before raising: request and access are intentionally distinct.
  atomic_json(self.log,{"events":self.events,"held_out_request_count":sum(x["is_held_out"] for x in self.events),"held_out_denied_count":sum(x["is_held_out"] and not x["granted"] for x in self.events),"held_out_access_count":sum(x["is_held_out"] and x["granted"] for x in self.events)})
  if not granted: raise PermissionError("held-out seed access denied")
def modes(N):return np.fft.fftfreq(N,1/N).astype(int)
def mask(N):
 k=modes(N);x,y=np.meshgrid(k,k,indexing="ij");return (abs(x)<=N//2-1)&(abs(y)<=N//2-1)
def forward(x):return np.fft.fft2(np.asarray(x,dtype=np.float64))/x.size
def inverse(h):return np.fft.ifft2(np.asarray(h,dtype=np.complex128)*h.size).real
def project(h):h=np.array(h,dtype=np.complex128,copy=True);h[~mask(h.shape[0])]=0;return h
def product(x,y):
 N=x.shape[0];P=2*N;A=np.zeros((P,P),complex);B=A.copy();u=forward(x);v=forward(y)
 for i in range(-N//2+1,N//2):
  for j in range(-N//2+1,N//2):A[i%P,j%P]=u[i%N,j%N];B[i%P,j%P]=v[i%N,j%N]
 C=np.fft.fft2(np.fft.ifft2(A*P*P)*np.fft.ifft2(B*P*P))/(P*P);H=np.zeros((N,N),complex)
 for i in range(-N//2+1,N//2):
  for j in range(-N//2+1,N//2):H[i%N,j%N]=C[i%P,j%P]
 return inverse(H)
def lap(x):
 N=x.shape[0];k=modes(N);a,b=np.meshgrid(k,k,indexing="ij");return inverse(-(a*a+b*b)*forward(x)*mask(N))
def grad(x):
 N=x.shape[0];k=modes(N);a,b=np.meshgrid(k,k,indexing="ij");h=forward(x)*mask(N);return inverse(1j*a*h),inverse(1j*b*h)
@dataclass(frozen=True)
class Params: lambda_phi:float=1.;v:float=1.;eta:float=.1;dt:float=.00125
def mu(psi,phi,p):
 p2=product(phi,phi);return -lap(psi)+psi-p.eta*p2,-lap(phi)+p.lambda_phi*product(phi,p2-p.v*p.v)-2*p.eta*product(phi,psi)
def energy(psi,phi,p):
 gx,gy=grad(psi);px,py=grad(phi);u=product(phi,phi)-p.v*p.v;dx=2*math.pi/psi.shape[0]
 return float(dx*dx*np.sum(.5*(gx*gx+gy*gy+psi*psi+px*px+py*py)+p.lambda_phi/4*product(u,u)-p.eta*product(product(phi,phi),psi)))
def imex(psi,phi,p,psi_zero=0.,one_way_psi=None):
 N=psi.shape[0];k=modes(N);a,b=np.meshgrid(k,k,indexing="ij");k2=a*a+b*b;p2=product(phi,phi)
 hp=(forward(psi)+p.dt*k2*p.eta*forward(p2))/(1+p.dt*k2*(k2+1))
 # In the nonvariational one_way arm, Phi sees the stored eta0 trajectory;
 # psi itself is returned by reference rather than re-integrated.
 phi_driver=psi if one_way_psi is None else np.asarray(one_way_psi,dtype=np.float64)
 hf=(forward(phi)+p.dt*forward(-p.lambda_phi*product(phi,p2-p.v*p.v)+2*p.eta*product(phi,phi_driver)))/(1+p.dt*k2)
 hp=project(hp);hf=project(hf);hp[0,0]=psi_zero
 return (np.array(one_way_psi,copy=True) if one_way_psi is not None else inverse(hp)),inverse(hf)
@dataclass
class Stats:
 psi_num:float=0.;psi_den:float=0.;phi_num:float=0.;phi_den:float=0.;feedback_num:float=0.;feedback_den:float=0.;a_num:float=0.;a_psi2:float=0.;a_q2:float=0.;samples:int=0
 def add(self,x,b,y,c,o,w):
  self.psi_num+=w*np.sum((x-b)**2);self.psi_den+=w*np.sum(b*b);self.phi_num+=w*np.sum((y-c)**2);self.phi_den+=w*np.sum(c*c);self.feedback_num+=w*np.sum((y-o)**2);self.feedback_den+=w*np.sum(o*o);q=y*y-np.mean(y*y);self.a_num+=w*np.sum(x*q);self.a_psi2+=w*np.sum(x*x);self.a_q2+=w*np.sum(q*q);self.samples+=1
 def ratios(self):
  ds=(self.psi_den,self.phi_den,self.feedback_den,self.a_psi2*self.a_q2)
  if any(not np.isfinite(x) or x<1e-12 for x in ds):raise RuntimeError("invalid endpoint denominator")
  return {"E_psi":(self.psi_num/self.psi_den)**.5,"E_Phi":(self.phi_num/self.phi_den)**.5,"E_feedback_Phi":(self.feedback_num/self.feedback_den)**.5,"A_full":self.a_num/(self.a_psi2*self.a_q2)**.5}
def bootstrap(values,raw):
 a=np.asarray(values,float);i=np.frombuffer(raw,dtype=np.uint8).reshape(10000,16)
 if a.shape!=(16,) or not np.all(np.isfinite(a)) or i.max()>15:raise RuntimeError("bad paired bootstrap")
 return np.mean(a[i],axis=1)
def atomic_json(path,data):
 p=Path(path);b=json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode();f=tempfile.NamedTemporaryFile(dir=p.parent,delete=False);f.write(b);f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,p);return hashlib.sha256(b).hexdigest()
def save_checkpoint(path,identity,psi,phi,step,time,stats):
 p=Path(path);f=tempfile.NamedTemporaryFile(dir=p.parent,suffix=".npz",delete=False);np.savez(f,identity=json.dumps(identity,sort_keys=True),psi=psi,phi=phi,step=step,time=time,stats=json.dumps(stats.__dict__,sort_keys=True));f.flush();os.fsync(f.fileno());f.close();os.replace(f.name,p)
def load_checkpoint(path,identity):
 x=np.load(path,allow_pickle=False)
 if json.loads(str(x["identity"]))!=identity:raise RuntimeError("resume identity mismatch")
 return x
def finalize(records,required,errors=()):
 reasons=list(errors);ids=[r.get("condition_id") for r in records]
 if set(ids)!=set(required) or len(ids)!=len(set(ids)):reasons.append("missing_or_duplicate_conditions")
 if any(not r.get("finite",False) for r in records):reasons.append("nonfinite_or_missing_stats")
 complete=not any(x in reasons for x in ("missing_or_duplicate_conditions","nonfinite_or_missing_stats"))
 return {"execution_complete":complete,"gate_pass":complete and not reasons,"failure_reasons":reasons}
