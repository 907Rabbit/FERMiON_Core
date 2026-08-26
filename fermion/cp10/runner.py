"""Safe CP10-R1 CLI. full is intentionally closed without a future launch record."""
from __future__ import annotations
import argparse,hashlib,json,platform,sys
from pathlib import Path
import numpy as np
from ._core import verify_frozen_bundle,frozen_kats,Params,imex,Stats,save_checkpoint,load_checkpoint
def _kat():
 got=frozen_kats(); exp={"zero":(0x6627E8D5,0xE169C58D,0xBC57AC4C,0x9B00DBD8),"psi":(0x64B845E3,0xC0D03EFF,0xA6048AFC,0x8D9FCFDD),"phi":(0x50A85EA5,0x3133A7DC,0xBFB41303,0x8DD66E54),"bootstrap":(0x6956EDEC,0x941E6BD1,0x4C0F997E,0x0C76C276)}
 if got!=exp: raise RuntimeError("Philox literal vector failure")
 return {k:[f"0x{x:08X}" for x in v] for k,v in got.items()}
def verify(root="."):
 p=verify_frozen_bundle(root); from .audits import run
 audits=run(root)
 if audits['status']!='PASS': raise RuntimeError('startup audit failure')
 return {"status":"PASS","protocol_id":"CP10-P0.8","philox":_kat(),"bootstrap_shape":[10000,16],"audits":audits,"held_out_access_count":0}
def _seed_guard(seed,allow=False):
 if 1001<=seed<=1016 and not allow: raise PermissionError("held-out seed access denied")
def smoke(root="."):
 p=verify_frozen_bundle(root);_kat();_seed_guard(1);N=32;rng=np.random.default_rng(1);psi=rng.normal(0,.01,(N,N));phi=rng.normal(0,.01,(N,N));z=float((np.fft.fft2(psi)[0,0]/(N*N)).real);out={};cp=Path(root)/"artifacts/cp10_r1_p0_8";cp.mkdir(parents=True,exist_ok=True)
 for arm,eta in (("eta0",0.),("full",.1),("one_way",.1)):
  a,b=imex(psi,phi,Params(eta=eta,dt=.00125),z,psi if arm=="one_way" else None);out[arm]={"finite":bool(np.all(np.isfinite(a)) and np.all(np.isfinite(b))),"steps":1}
 s=Stats();s.add(out and psi,psi,phi,phi,phi,1.);identity={"protocol":"CP10-P0.8","condition":"NONSCIENTIFIC:s1"};ck=cp/"smoke_resume.npz";save_checkpoint(ck,identity,psi,phi,1,.00125,s);load_checkpoint(ck,identity)
 return {"scientific_use":False,"protocol_condition":False,"verdict_eligible":False,"requested_seeds":[1],"held_out_access_count":0,"arms":out,"checkpoint_resume":"PASS"}
def main(argv=None):
 q=argparse.ArgumentParser();sp=q.add_subparsers(dest="cmd",required=True);sp.add_parser("verify");s=sp.add_parser("smoke");s.add_argument("--allow-calibration-smoke",action="store_true");f=sp.add_parser("full");f.add_argument("--launch-record",required=True);a=q.parse_args(argv)
 if a.cmd=="verify": print(json.dumps(verify(),sort_keys=True));return
 if a.cmd=="smoke":
  if not a.allow_calibration_smoke: raise SystemExit("smoke requires --allow-calibration-smoke")
  print(json.dumps(smoke(),sort_keys=True));return
 raise SystemExit("full execution is gated: a future detached authorized launch record is required")
if __name__=="__main__":main()
