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
def record_indices(dt: float) -> tuple[int,...]: return tuple(round(t/dt) for t in RECORD_TIMES)
def l2(a: np.ndarray) -> float: return float(np.sqrt((2*np.pi/32)**2*np.sum(np.asarray(a, dtype=np.float64)**2)))
def weights() -> np.ndarray: return np.array([.025]+[.05]*19+[.025])
def trajectory_norm(samples: np.ndarray) -> float: return float(np.sqrt(np.sum(weights()*np.array([l2(x)**2 for x in samples]))))
def relative_final(a,b): return l2(a-b)/max(l2(b),1e-12)
def relative_trajectory(a,b): return trajectory_norm(a-b)/max(trajectory_norm(b),1e-12)
def relative_modal_max(a,b): return float(np.max(abs(a-b))/max(float(np.max(abs(b))),1e-12))
def medium_fine(medium, fine): return {"final":relative_final(medium[-1],fine[-1]),"trajectory":relative_trajectory(medium,fine)}
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
