"""Frozen CP10-P0.10 Oracle-A primitives.  Execution requires a future launch record."""
from __future__ import annotations
import hashlib, json, os, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "protocols/cp10_p0_10_FREEZE_RECEIPT.json"
CHECKSUM = ROOT / "artifacts/cp10_p0_10_FREEZE_RECEIPT.json.sha256"
RECEIPT_SHA256 = "482D3EA675350BA359E66B61D381D0CA929CA7A2E02B56F5D07848C763506540"
RUNS = (
    ("oracle_a_n032_dt0p0025_coarse", 0.0025, 400, "coarse"),
    ("oracle_a_n032_dt0p00125_medium", 0.00125, 800, "medium"),
    ("oracle_a_n032_dt0p000625_fine", 0.000625, 1600, "fine"),
)
RECORD_TIMES = tuple(i / 20 for i in range(21))
FROZEN_SPECS = tuple({"run_id":i,"N":32,"dt":d,"T":1.0,"step_count":n,"role":r,"record_times":RECORD_TIMES,"record_indices":tuple(round(t/d) for t in RECORD_TIMES)} for i,d,n,r in RUNS)
_CAP_SENTINEL=object()
class _FrozenAuthorization:
    def __init__(self,sentinel,**kw):
        if sentinel is not _CAP_SENTINEL: raise PermissionError("private capability")
        self.__dict__.update(kw)
def frozen_json_specs():
    return [{"run_id":x["run_id"],"N":32,"dt":float(x["dt"]),"T":1.0,"step_count":int(x["step_count"]),"role":x["role"],"record_times":[float(t) for t in RECORD_TIMES],"record_indices":[int(i) for i in x["record_indices"]]} for x in FROZEN_SPECS]

def _reject_constant(value: str) -> None: raise ValueError(f"non-finite JSON value: {value}")
def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
def strict_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
def sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def atomic_bytes(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary): os.unlink(temporary)
        raise
def atomic_json(path: Path, value: Any) -> None: atomic_bytes(path, canonical_json(value))

def verify_frozen_bundle(root: Path = ROOT) -> dict[str, Any]:
    receipt_path, checksum_path = root / RECEIPT.relative_to(ROOT), root / CHECKSUM.relative_to(ROOT)
    if sha256(receipt_path) != RECEIPT_SHA256: raise RuntimeError("freeze receipt hash mismatch")
    line = checksum_path.read_bytes()
    expected = f"{RECEIPT_SHA256}  protocols/cp10_p0_10_FREEZE_RECEIPT.json\n".encode("ascii")
    if line != expected: raise RuntimeError("detached checksum mismatch")
    receipt = strict_json(receipt_path)
    if receipt["status"] != "FROZEN" or receipt["bundle_member_count"] != 12: raise RuntimeError("invalid freeze receipt")
    for member in receipt["bundle_members"]:
        path = root / member["path"]
        if not path.is_file() or path.stat().st_size != member["byte_length"] or sha256(path) != member["sha256"]:
            raise RuntimeError(f"frozen bundle mismatch: {member['path']}")
        if member["strict_json_status"] == "PASS": strict_json(path)
    return receipt

def retained_mask(n: int = 32) -> np.ndarray:
    modes = np.fft.fftfreq(n, d=1 / n).astype(int)
    kx, ky = np.meshgrid(modes, modes, indexing="ij")
    return np.maximum(abs(kx), abs(ky)) <= n // 2 - 1
def enforce_nyquist(a: np.ndarray) -> None:
    a[a.shape[0] // 2, :] = 0; a[:, a.shape[1] // 2] = 0
def hermitian_correct(a: np.ndarray) -> float:
    before = a.copy(); n = a.shape[0]
    for i in range(n):
        for j in range(n):
            ii, jj = (-i) % n, (-j) % n
            if (i, j) <= (ii, jj):
                value = 0.5 * (a[i, j] + np.conj(a[ii, jj])); a[i, j] = value; a[ii, jj] = np.conj(value)
    correction = np.linalg.norm(a - before) / max(np.linalg.norm(before), 1e-300)
    if correction > 1e-13: raise RuntimeError("Hermitian correction exceeds frozen threshold")
    return float(correction)
def imex_step(old: np.ndarray, dt: float, initial_zero: complex) -> tuple[np.ndarray, float]:
    if old.dtype != np.dtype("<c16") or not np.isfinite(old).all(): raise ValueError("complex128 finite state required")
    n = old.shape[0]; modes = np.fft.fftfreq(n, d=1/n); kx, ky = np.meshgrid(modes, modes, indexing="ij"); k2 = kx*kx + ky*ky
    new = np.zeros_like(old); keep = retained_mask(n); new[keep] = old[keep] / (1 + dt * k2[keep] * (k2[keep] + 1)); new[0,0] = initial_zero
    enforce_nyquist(new); return new, hermitian_correct(new)
def analytic(initial: np.ndarray, t: float) -> np.ndarray:
    n=initial.shape[0]; k=np.fft.fftfreq(n,d=1/n); x,y=np.meshgrid(k,k,indexing="ij"); k2=x*x+y*y
    return initial * np.exp(-k2*(k2+1)*t)
def record_indices(dt: float, times=RECORD_TIMES, step_count=None) -> tuple[int,...]:
    if not np.isfinite(dt) or dt <= 0: raise ValueError("invalid dt")
    x=tuple(times); tol=8*np.finfo(float).eps
    if not x or x[0]!=0 or any(not np.isfinite(t) for t in x) or any(b<=a for a,b in zip(x,x[1:])): raise ValueError("invalid record times")
    out=tuple(int(round(t/dt)) for t in x)
    if any(abs(t-i*dt)>tol*max(1,abs(t)) for t,i in zip(x,out)) or len(set(out))!=len(out) or out[0]!=0: raise ValueError("nonintegral record schedule")
    if step_count is not None and out[-1]!=step_count: raise ValueError("terminal step mismatch")
    return out
def l2(a: np.ndarray) -> float:
    a=np.asarray(a)
    if a.ndim!=2 or a.shape[0]!=a.shape[1] or not a.size or np.iscomplexobj(a) or not np.isfinite(a).all(): raise ValueError("finite real square physical field required")
    return float(np.sqrt((2*np.pi/a.shape[0])**2*np.sum(a*a)))
def weights() -> np.ndarray: return np.array([.025]+[.05]*19+[.025])
def trajectory_norm(samples: np.ndarray) -> float:
    if len(samples)!=21: raise ValueError("frozen trajectory requires 21 records")
    w = weights()
    return float(np.sqrt(np.sum(w*np.array([l2(x)**2 for x in samples]))))
def relative_final(a,b): return l2(a-b)/max(l2(b),1e-12)
def relative_trajectory(a,b): return trajectory_norm(a-b)/max(trajectory_norm(b),1e-12)
def relative_modal_max(a,b): return float(np.max(abs(a-b))/max(float(np.max(abs(b))),1e-12))
def medium_fine(medium, fine): return {"final":relative_final(medium[-1],fine[-1]),"trajectory":relative_trajectory(medium,fine)}
def synthetic_trajectory_norm(samples, times):
    t=np.asarray(times,float)
    if len(samples)!=len(t) or len(t)<2 or not np.isfinite(t).all() or np.any(np.diff(t)<=0): raise ValueError("invalid synthetic trajectory times")
    w=np.empty(len(t));w[0]=(t[1]-t[0])/2;w[-1]=(t[-1]-t[-2])/2;w[1:-1]=(t[2:]-t[:-2])/2
    return float(np.sqrt(np.sum(w*np.array([l2(x)**2 for x in samples]))))
def validate_launch_record(launch_record_path: Path, expected_launch_record_sha256: str, root: Path=ROOT) -> _FrozenAuthorization:
    p=Path(launch_record_path)
    if not p.is_file(): raise RuntimeError("launch record missing")
    if sha256(p)!=expected_launch_record_sha256.upper(): raise RuntimeError("launch record hash mismatch")
    x=strict_json(p); expected=[s["run_id"] for s in FROZEN_SPECS]
    required={"protocol_id":"CP10-P0.10","status":"AUTHORIZED","authorization_scope":"ORACLE_A_THREE_RUN_VERIFICATION_ONLY","freeze_receipt_sha256":RECEIPT_SHA256,"solver_sha256":sha256(root/"fermion/cp10/oracle_a_p0_10.py"),"launcher_sha256":sha256(root/"fermion/cp10/oracle_a_launcher_p0_10.py"),"source_manifest_sha256":sha256(root/"artifacts/cp10_p0_10_oracle_a/source_manifest.json"),"output_root":"artifacts/cp10_p0_10_oracle_a/"}
    if any(x.get(k)!=v for k,v in required.items()) or x.get("run_ids")!=expected or x.get("run_tuples")!=frozen_json_specs() or (root/x["output_root"]/"oracle_a_result.json").exists(): raise RuntimeError("invalid launch record")
    if any(x.get(k,True) for k in ("oracle_b","scientific_conditions","held_out_access","bootstrap")) or not x.get("execution_id") or not x.get("utc_authorization_timestamp"): raise RuntimeError("launch scope invalid")
    return _FrozenAuthorization(_CAP_SENTINEL,launch_hash=expected_launch_record_sha256.upper(),source_hash=required["source_manifest_sha256"],receipt_hash=RECEIPT_SHA256,output_root=x["output_root"],tuples=frozen_json_specs(),execution_id=x["execution_id"],timestamp=x["utc_authorization_timestamp"])
def _integrate_frozen(spec, initial, authorization):
    if not isinstance(authorization,_FrozenAuthorization) or authorization.receipt_hash!=RECEIPT_SHA256 or authorization.source_hash!=sha256(ROOT/"artifacts/cp10_p0_10_oracle_a/source_manifest.json") or authorization.tuples!=frozen_json_specs() or authorization.output_root!="artifacts/cp10_p0_10_oracle_a/": raise PermissionError("invalid frozen capability")
    if spec not in FROZEN_SPECS: raise PermissionError("wrong frozen spec")
    return _integrate_core(spec,initial)
def validate_completed_run(run, initial):
    required={"spectral","physical","exact_spectral","exact_physical","metrics"}
    if required-set(run) or any(np.asarray(run[k]).shape!=(21,32,32) for k in required-{"metrics"}): raise RuntimeError("incomplete run arrays")
    m=run["metrics"]
    if any(m[k] is None for k in ("final_relative_l2","trajectory_relative_l2","modal_max","zero_mode_error","nyquist_max","correction_max","nonfinite_count")): raise RuntimeError("dropped metric")
    if not np.isfinite(run["spectral"]).all() or m["nyquist_max"]!=0 or m["correction_max"]>1e-13: raise RuntimeError("hard stop")
    if not np.array_equal(run["spectral"][0],initial): raise RuntimeError("fixture identity")
    return True
def _integrate_core(spec: dict[str,Any], initial: np.ndarray) -> dict[str,Any]:
    """Numerical core only: no authorization and no writing."""
    state=np.array(initial,dtype="<c16",copy=True); records=[state.copy()]; corrections=[]; schedule=spec["record_indices"]
    for step in range(1,spec["step_count"]+1):
        state,corr=imex_step(state,spec["dt"],initial[0,0]); corrections.append(corr)
        if step in schedule: records.append(state.copy())
    if len(records)!=len(schedule) or not np.isfinite(state).all(): raise RuntimeError("record or finite failure")
    spectral=np.asarray(records,dtype="<c16"); physical=np.asarray([np.real(np.fft.ifft2(x)*spec["N"]**2) for x in spectral],dtype="<f8"); exact=np.asarray([analytic(initial,t) for t in spec["record_times"]],dtype="<c16")
    return {"spectral":spectral,"physical":physical,"exact_spectral":exact,"exact_physical":np.asarray([np.real(np.fft.ifft2(x)*spec["N"]**2) for x in exact],dtype="<f8"),"corrections":corrections}
def integrate_synthetic(spec: dict[str,Any], initial: np.ndarray) -> dict[str,Any]:
    if spec["run_id"] in {x["run_id"] for x in FROZEN_SPECS}: raise PermissionError("frozen specification integration requires launch record")
    if spec["N"]>8 or spec["step_count"]>4: raise ValueError("synthetic integration limits")
    return _integrate_core(spec,initial)
def run_metrics(result:dict[str,Any]) -> dict[str,Any]:
    n,e=result["spectral"],result["exact_spectral"]; p,ep=result["physical"],result["exact_physical"]; keep=retained_mask(n.shape[-1])
    return {"final_relative_l2":relative_final(p[-1],ep[-1]),"trajectory_relative_l2":relative_trajectory(p,ep),"modal_max":relative_modal_max(n[:,keep],e[:,keep]),"zero_mode_error":float(np.max(abs(n[:,0,0]-e[:,0,0]))),"nyquist_max":float(max(abs(n[:,:,n.shape[-1]//2]).max(),abs(n[:,n.shape[-1]//2,:]).max())),"correction_max":max(result["corrections"],default=0.0),"nonfinite_count":int(n.size-np.isfinite(n).sum()),"step_count":len(result["corrections"]),"record_count":len(n)}
def aggregate(fine,medium_fine_metrics,all_ids,coarse_present=True):
    return coarse_present and all_ids==[x["run_id"] for x in FROZEN_SPECS] and fine["final_relative_l2"]<=.02 and fine["trajectory_relative_l2"]<=.02 and fine["modal_max"]<=.02 and medium_fine_metrics["final"]<=.02 and medium_fine_metrics["trajectory"]<=.02 and fine["zero_mode_error"]<=1e-12 and fine["nyquist_max"]==0 and fine["correction_max"]<=1e-13 and fine["nonfinite_count"]==0
def load_fixtures(root: Path = ROOT) -> dict[str,np.ndarray]:
    receipt=verify_frozen_bundle(root); members={Path(x["path"]).name:x for x in receipt["bundle_members"]}
    def load(name,dtype):
        member=members[name]; raw=(root/member["path"]).read_bytes();
        if len(raw)!=member["byte_length"]: raise RuntimeError("fixture length")
        return np.frombuffer(raw,dtype=dtype).copy().reshape(32,32)
    return {"psi_spectral":load("cp10_p0_10_oracle_a_initial_psi_spectral.bin","<c16"),"psi_physical":load("cp10_p0_10_oracle_a_initial_psi_physical.bin","<f8"),"Phi_spectral":load("cp10_p0_10_oracle_a_initial_Phi_spectral.bin","<c16"),"Phi_physical":load("cp10_p0_10_oracle_a_initial_Phi_physical.bin","<f8")}
def build_run_artifacts(run_id: str, spectral: np.ndarray, physical: np.ndarray) -> dict[str, Any]:
    if spectral.shape != (21,32,32) or physical.shape != (21,32,32): raise ValueError("frozen trajectory shapes required")
    return {"run_id":run_id,"arrays":{"spectral":{"dtype":"<c16","shape":[21,32,32],"sha256":hashlib.sha256(np.ascontiguousarray(spectral).tobytes()).hexdigest().upper()},"physical":{"dtype":"<f8","shape":[21,32,32],"sha256":hashlib.sha256(np.ascontiguousarray(physical).tobytes()).hexdigest().upper()}}}
def run_oracle_a(*_args, authorization: Any = None, **_kwargs):
    if authorization is None: raise PermissionError("P0.10 has no Oracle-A launch record")
    raise PermissionError("Oracle-A execution remains unauthorized")
