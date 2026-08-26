import hashlib,json
from pathlib import Path
import numpy as np
import pytest
from fermion.cp10.frozen_protocol import verify_frozen_bundle
from fermion.cp10.philox import frozen_kats,modal_initializer
from fermion.cp10.spectral import forward,inverse,gradient,padded_product,retained_mask
from fermion.cp10.model import Params,step
from fermion.cp10.bootstrap import ci
from fermion.cp10.checkpointing import save_checkpoint,load_checkpoint
from fermion.cp10.diagnostics import Stats
from fermion.cp10.finalizer import finalize
from fermion.cp10._core import SeedAccess
from fermion.cp10.audits import run as run_audits

ROOT=Path(__file__).resolve().parents[1]
def test_frozen_bundle_and_conditions():
 p=verify_frozen_bundle(ROOT); assert p.receipt['protocol_status']=='FROZEN'; assert len(p.bootstrap)==160000
def test_philox_kats_and_bootstrap():
 assert frozen_kats()['zero']==(0x6627E8D5,0xE169C58D,0xBC57AC4C,0x9B00DBD8)
 p=verify_frozen_bundle(ROOT); assert np.frombuffer(p.bootstrap,dtype=np.uint8).max()==15
def test_strict_json_and_modal_reuse(tmp_path):
 from fermion.cp10.frozen_protocol import strict
 p=tmp_path/'bad.json';p.write_text('{"x":1,"x":2}')
 with pytest.raises(ValueError): strict(p)
 a=modal_initializer(1,0x50534931,32);b=modal_initializer(1,0x50534931,64)
 assert abs(np.sqrt(np.sum(abs(a)**2))-.05)<1e-15 and max(abs(a[i,j]-a[-i%32,-j%32].conjugate()) for i in range(32) for j in range(32))<1e-12
 assert np.allclose(a[1,2],b[1,2])
 p.write_bytes(b'{"x":NaN}')
 with pytest.raises(ValueError): strict(p)
 p.write_bytes(b'\xff')
 with pytest.raises(UnicodeDecodeError): strict(p)
def test_seed_denial_is_logged_before_access(tmp_path):
 s=SeedAccess(tmp_path/'seed.json')
 with pytest.raises(PermissionError): s.request(1001,requesting_component='test')
 x=json.loads((tmp_path/'seed.json').read_text());assert x['held_out_request_count']==1 and x['held_out_denied_count']==1 and x['held_out_access_count']==0 and not x['events'][0]['granted']
def test_independent_startup_audits():
 a=run_audits(ROOT);assert a['status']=='PASS';assert [x['direct_support_count']for x in a['product_fixtures']]==[33,86,50,86];assert a['product_fixtures'][-1]['anchors']['1,2']['actual'][0]==pytest.approx(-.115672625,abs=1e-15)
def test_fft_parseval_derivative_and_padded_product():
 N=32;x=np.arange(N)*2*np.pi/N;X,Y=np.meshgrid(x,x,indexing='ij');a=np.cos(2*X+Y)
 assert np.max(abs(inverse(forward(a))-a))<1e-14
 assert abs((2*np.pi/N)**2*np.sum(a*a)-(2*np.pi)**2*np.sum(abs(forward(a))**2))<1e-12
 gx,_=gradient(a);assert np.max(abs(gx+2*np.sin(2*X+Y)))<1e-12
 assert np.max(abs(padded_product(a,a)-a*a))<1e-12
def test_nyquist_and_one_way_identity():
 N=32;a=np.zeros((N,N));b=np.ones((N,N))*.01;h=forward(a);h[N//2,0]=1; assert not retained_mask(N)[N//2,0]
 out,_=step(a,b,Params(),0.,a);assert np.array_equal(out,a)
def test_stats_bootstrap_checkpoint_and_finalizer(tmp_path):
 s=Stats();a=np.array([[1.,2.],[3.,4.]]);s.add(2*a,a,3*a,a,a,1.);assert s.ratios()['E_psi']>0
 p=verify_frozen_bundle(ROOT);x=np.arange(16.,dtype=float);assert np.array_equal(ci(x,p.bootstrap),ci(x,p.bootstrap))
 ident={'x':'frozen'};f=tmp_path/'c.npz';save_checkpoint(f,ident,a,a,1,.1,s);assert load_checkpoint(f,ident)['step']==1
 with pytest.raises(RuntimeError):load_checkpoint(f,{'x':'changed'})
 assert finalize([],['x'])['execution_complete'] is False
