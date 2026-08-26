import shutil
from pathlib import Path
import numpy as np
import pytest
from fermion.cp10 import oracle_a_p0_10 as o
from fermion.cp10 import oracle_a_launcher_p0_10 as launcher

def test_frozen_bundle_and_fixtures():
    assert launcher.verify()["members"] == 12
    f=o.load_fixtures(); assert f["psi_spectral"].dtype == np.dtype("<c16")
    assert f["psi_spectral"].shape == (32,32) and not f["Phi_spectral"].any()

def test_launcher_aborts_before_solver_import(tmp_path):
    root=tmp_path; shutil.copytree(o.ROOT/"protocols",root/"protocols"); shutil.copytree(o.ROOT/"artifacts",root/"artifacts")
    p=root/"protocols/cp10_p0_10_FREEZE_RECEIPT.json"; p.write_bytes(p.read_bytes()+b"x")
    with pytest.raises(RuntimeError): launcher.verify(root)

def test_runs_schedule_and_step():
    assert [x[0] for x in o.RUNS] == ["oracle_a_n032_dt0p0025_coarse","oracle_a_n032_dt0p00125_medium","oracle_a_n032_dt0p000625_fine"]
    assert o.record_indices(.0025) == tuple(range(0,401,20)); assert o.record_indices(.000625) == tuple(range(0,1601,80))
    a=np.zeros((32,32),"<c16");a[1,0]=2;a[-1,0]=2;a[0,0]=3
    b,c=o.imex_step(a,.1,a[0,0]);assert b[1,0] == pytest.approx(2/(1+.2));assert b[0,0]==3 and c==0
    bad=a.copy();bad[-1,0]=0
    with pytest.raises(RuntimeError):o.imex_step(bad,.1,bad[0,0])

def test_nyquist_hermitian_analytic_and_metrics():
    a=np.zeros((32,32),"<c16");a[16,1]=2;o.enforce_nyquist(a);assert not a.any()
    a[1,2]=1+2j;a[-1,-2]=1-2j;assert o.hermitian_correct(a)==0
    assert o.analytic(a,.5)[1,2] == pytest.approx((1+2j)*np.exp(-30*.5))
    z=np.zeros((21,32,32));assert o.relative_final(z,z)==o.relative_trajectory(z,z)==o.relative_modal_max(z,z)==0
    q=z.copy();q[0,0,0]=1;assert o.relative_trajectory(q,z)>0 and o.medium_fine(q,z)["final"]==0
    assert np.array_equal(o.weights(),np.array([.025]+[.05]*19+[.025]))

def test_nonfinite_output_and_execution_gate(tmp_path):
    a=np.zeros((32,32),"<c16");a[1,1]=np.nan
    with pytest.raises(ValueError):o.imex_step(a,.1,0)
    with pytest.raises(PermissionError):o.run_oracle_a()
    s=np.zeros((21,32,32),"<c16");p=np.zeros((21,32,32),"<f8");x=o.build_run_artifacts("x",s,p);assert x["arrays"]["spectral"]["shape"]==[21,32,32]
    assert not hasattr(o,"resume") and not hasattr(o,"checkpoint")
