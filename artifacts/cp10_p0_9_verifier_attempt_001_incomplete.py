"""Standalone P0.9 prefreeze verifier; deliberately imports no fermion code."""
import hashlib,json,platform,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def strict(p):
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise ValueError(k)
   d[k]=v
  return d
 return json.loads(p.read_bytes().decode('utf-8','strict'),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError(x)))
def H(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fwd(x):return np.fft.fft2(np.asarray(x,dtype=np.float64))/x.size
def inv(h):return np.fft.ifft2(np.asarray(h,dtype=np.complex128)*h.size).real
def mask(N):
 k=np.fft.fftfreq(N,1/N);a,b=np.meshgrid(k,k,indexing='ij');return(abs(a)<=N//2-1)&(abs(b)<=N//2-1)
def prod(x,y):
 N=len(x);P=2*N;A=np.zeros((P,P),complex);B=A.copy();u=fwd(x);v=fwd(y)
 for i in range(-N//2+1,N//2):
  for j in range(-N//2+1,N//2):A[i%P,j%P]=u[i%N,j%N];B[i%P,j%P]=v[i%N,j%N]
 C=np.fft.fft2(np.fft.ifft2(A*P*P)*np.fft.ifft2(B*P*P))/(P*P);Z=np.zeros((N,N),complex)
 for i in range(-N//2+1,N//2):
  for j in range(-N//2+1,N//2):Z[i%N,j%N]=C[i%P,j%P]
 return inv(Z)
def main():
 c=strict(ROOT/'protocols/cp10_p0_9_ORACLE_FREEZE_CANDIDATE.json');m=strict(ROOT/'protocols/cp10_p0_9_condition_manifest.json');
 # The candidate describes required future execution; this verifier intentionally fails closed
 # unless all eight runs, full per-array provenance, and every metric are implemented here.
 out={'protocol_id':'CP10-P0.9','verifier_source_sha256':H(__file__),'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'byteorder':sys.byteorder},'imports_fermion_cp10':False,'provenance_hashes':c['revision_provenance']['p0_8_authoritative_hashes'],'status':'FAIL','failure_reasons':['independent eight-run oracle integration and complete per-array metric/provenance capture not yet implemented'], 'assertion':'No CP10 condition, calibration, held-out, bootstrap, or CP11 operation was executed.'}
 p=ROOT/'artifacts/cp10_p0_9_oracle_verification.json';p.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
if __name__=='__main__':main()
