"""Frozen CP10-P0.10 Oracle-A primitives.  Execution requires a future launch record."""
from __future__ import annotations
import hashlib, json, os, tempfile
import datetime
import math
import stat
import re
import unicodedata
from decimal import Decimal
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Callable
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_OUTPUT_ROOT_RELATIVE = "artifacts/cp10_p0_10_oracle_a"
PRODUCTION_LAUNCH_RECORD_FILENAME = "oracle_a_launch_record.json"
PRODUCTION_LAUNCH_RECORD_RELATIVE = f"{PRODUCTION_OUTPUT_ROOT_RELATIVE}/{PRODUCTION_LAUNCH_RECORD_FILENAME}"
PRODUCTION_TEMP_PREFIX = ".oracle_a_prod_"
PRODUCTION_ROOT_TARGETS = ("oracle_a_environment.json","oracle_a_source_manifest.json","oracle_a_result.json","oracle_a_execution_receipt.json","oracle_a_stdout.txt","oracle_a_stderr.txt")
RECEIPT = ROOT / "protocols/cp10_p0_10_FREEZE_RECEIPT.json"
CHECKSUM = ROOT / "artifacts/cp10_p0_10_FREEZE_RECEIPT.json.sha256"
RECEIPT_SHA256 = "482D3EA675350BA359E66B61D381D0CA929CA7A2E02B56F5D07848C763506540"
RUNS = (
    ("oracle_a_n032_dt0p0025_coarse", 0.0025, 400, "coarse"),
    ("oracle_a_n032_dt0p00125_medium", 0.00125, 800, "medium"),
    ("oracle_a_n032_dt0p000625_fine", 0.000625, 1600, "fine"),
)
PRODUCTION_RUN_TARGETS = tuple(f"{run_id}/{run_id}_{suffix}" for run_id,_,_,_ in RUNS for suffix in ("psi_numerical_spectral.bin","psi_exact_spectral.bin","psi_numerical_physical.bin","psi_exact_physical.bin","array_manifest.json","metrics.json"))
PRODUCTION_CANDIDATE_TARGETS = PRODUCTION_ROOT_TARGETS + PRODUCTION_RUN_TARGETS
PRODUCTION_TARGETS = (PRODUCTION_LAUNCH_RECORD_FILENAME,) + PRODUCTION_CANDIDATE_TARGETS
_PRELAUNCH_ROOT_TEXT=str(ROOT)
_PRELAUNCH_OUTPUT_TEXT=str(ROOT/PRODUCTION_OUTPUT_ROOT_RELATIVE)
_PRELAUNCH_CONTAINMENT=tuple(str(ROOT/PRODUCTION_OUTPUT_ROOT_RELATIVE/target) for target in PRODUCTION_CANDIDATE_TARGETS)
PRODUCTION_CANDIDATE_TARGETS_SHA256 = "F1C34EE79719ED7809CF074DFDA3830C01CB54DFBD6D3D3DF1BE8C719874458C"
PRODUCTION_TARGETS_SHA256 = "E34589D052A42DFFD8B9A5EA7D1EAB89E487EB1168A885116407C46002078639"
FILESYSTEM_CONTRACT_VERSION = "cp10-p0.10-oracle-a-filesystem-contract-d1a-v1"
PRODUCTION_SOURCE_MANIFEST_RELATIVE = "artifacts/cp10_p0_10_oracle_a/source_manifest.json"
PRODUCTION_SOURCE_MANIFEST_SCHEMA = "cp10-p0.10-oracle-a-source-manifest-d1b-v1"
PRELAUNCH_AUTHORITY_EVENTS = (
    "freeze_receipt",
    "detached_checksum",
    "bundle_members",
    "solver_hash",
    "launcher_hash",
    "source_manifest",
    "filesystem_contract",
    "launch_record_path",
    "launch_record_hash",
    "launch_record_parse",
    "launch_payload",
    "freeze_receipt_recheck",
    "detached_checksum_recheck",
    "bundle_members_recheck",
    "solver_hash_recheck",
    "launcher_hash_recheck",
    "source_manifest_recheck",
    "filesystem_contract_recheck",
    "authorized_pre_core",
)
class FilesystemAuthorizationError(ValueError): pass
@dataclass(frozen=True)
class FilesystemPathReport:
    project_root: str; output_root: str; targets: tuple[str,...]; target_set_sha256: str; containment: tuple[str,...]; reparse_findings: tuple[str,...]; status: str; collisions: tuple[str,...]=(); reserved_temporary_findings: tuple[str,...]=()
def _scan_production_collisions(output_root, targets, *, lstat_fn=os.lstat):
    try:
        parents=sorted({(Path(output_root)/target).parent for target in targets},key=str); collisions=[]; temporary=[]
        for target in targets:
            path=Path(output_root)/target
            try: lstat_fn(path); collisions.append(target)
            except FileNotFoundError: pass
        for parent in parents:
            if parent.is_dir():
                for child in parent.iterdir():
                    if child.name.startswith(PRODUCTION_TEMP_PREFIX): temporary.append(child.relative_to(output_root).as_posix())
        return tuple(sorted(collisions)),tuple(sorted(temporary))
    except OSError as exc: raise FilesystemAuthorizationError('collision inspection') from exc
def _validate_filesystem_paths(project_root, output_root_relative, targets, *, lstat_fn=os.lstat, resolve_fn=lambda p: Path(p).resolve()):
    if not isinstance(project_root,Path): project_root=Path(project_root)
    if output_root_relative != PRODUCTION_OUTPUT_ROOT_RELATIVE or tuple(targets) not in (PRODUCTION_CANDIDATE_TARGETS,PRODUCTION_TARGETS): raise FilesystemAuthorizationError('immutable targets required')
    expected=PRODUCTION_CANDIDATE_TARGETS_SHA256 if len(targets)==24 else PRODUCTION_TARGETS_SHA256
    if hashlib.sha256(canonical_json(sorted(targets))).hexdigest().upper()!=expected: raise FilesystemAuthorizationError('target hash')
    root=resolve_fn(project_root); out=project_root/output_root_relative
    if not out.exists() or not out.is_dir(): raise FilesystemAuthorizationError('output root')
    def inspect(p):
        q=p
        while not q.exists(): q=q.parent
        while True:
            s=lstat_fn(q)
            if stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400: raise FilesystemAuthorizationError('reparse path')
            if q==project_root: break
            q=q.parent
    inspect(out); findings=[]
    for target in targets:
        if not isinstance(target,str) or not target or '\x00' in target or '\\' in target or ':' in target or target.startswith(('/', '\\\\')) or any(x in ('','.','..') for x in target.split('/')): raise FilesystemAuthorizationError('lexical target')
        p=out/target; inspect(p)
        try:
            resolve_fn(p).relative_to(root); resolve_fn(p).relative_to(resolve_fn(out))
        except ValueError: raise FilesystemAuthorizationError('resolved escape') from None
        findings.append(str(p))
    collisions,temporary=_scan_production_collisions(out,targets,lstat_fn=lstat_fn)
    if collisions or temporary: raise FilesystemAuthorizationError('production collision')
    return FilesystemPathReport(str(root),str(resolve_fn(out)),tuple(targets),expected,tuple(findings),(), 'PASS',collisions,temporary)
def production_filesystem_contract(): return _validate_filesystem_paths(ROOT,PRODUCTION_OUTPUT_ROOT_RELATIVE,PRODUCTION_TARGETS)
RECORD_TIMES = tuple(i / 20 for i in range(21))
FROZEN_SPECS = ()  # derived compatibility view, initialized after RunSpec validation
_CAP_SENTINEL=object()
class _FrozenAuthorization:
    def __init__(self,sentinel,**kw):
        if sentinel is not _CAP_SENTINEL: raise PermissionError("private capability")
        self.__dict__.update(kw)
def frozen_json_specs(): return [x.to_json() for x in FROZEN_RUN_SPECS]
RUNSPEC_FIELD_SET=frozenset({"run_id","N","dt","T","step_count","role","record_times","record_indices"})
def _normalize_candidate_runs(oracle_a):
    times=oracle_a.get('record_times'); rec=oracle_a.get('recording')
    if not isinstance(times,list) or len(times)!=21 or times[0]!=0 or times[-1]!=1 or any(not isinstance(x,(int,float)) or not np.isfinite(x) for x in times) or any(b<=a for a,b in zip(times,times[1:])) or not isinstance(rec,dict) or rec.get('expected_record_count')!=21 or not isinstance(rec.get('integer_step_counts_per_dt'),dict): raise ValueError('candidate shared recording')
    schedules=rec['integer_step_counts_per_dt']; expected={'N','T','comparison_targets','dt','expected_record_count','refinement_role','run_id','step_count'}; specs=[]; audit=[]
    for ordinal,run in enumerate(oracle_a.get('runs',[])):
        if not isinstance(run,dict) or set(run)!=expected or run['expected_record_count']!=21 or run['refinement_role'] not in ('coarse','medium','fine') or not isinstance(run['comparison_targets'],list) or any(not isinstance(x,str) for x in run['comparison_targets']): raise ValueError('candidate run schema')
        matches=[k for k in schedules if Decimal(k)==Decimal(str(run['dt']))]
        if len(matches)!=1: raise ValueError('candidate dt schedule')
        indices=schedules[matches[0]]; payload={'run_id':run['run_id'],'N':run['N'],'dt':run['dt'],'T':run['T'],'step_count':run['step_count'],'role':run['refinement_role'],'record_times':times,'record_indices':indices}; spec=RunSpec.from_json(payload); specs.append(spec)
        audit.append({'ordinal':ordinal,'original_run':run,'original_run_sha256':hashlib.sha256(canonical_json(run)).hexdigest().upper(),'normalized_runspec':spec.to_json(),'schedule_key':matches[0],'record_times_sha256':hashlib.sha256(canonical_json(times)).hexdigest().upper(),'record_indices_sha256':hashlib.sha256(canonical_json(indices)).hexdigest().upper(),'comparison_targets':run['comparison_targets'],'comparison_targets_sha256':hashlib.sha256(canonical_json(run['comparison_targets'])).hexdigest().upper(),'runspec_equal':spec==FROZEN_RUN_SPECS[ordinal]})
    if tuple(specs)!=FROZEN_RUN_SPECS:return tuple(specs),audit,False
    return tuple(specs),audit,True
def candidate_run_authority(root:Path=ROOT):
    p=root/'protocols/cp10_p0_10_ORACLE_A_COMPLETION_CANDIDATE.json'
    if sha256(p)!="E9B1329D95DBDD5FBB8168416A7145E62D684BD66C35F1C19629823039179759": raise RuntimeError('candidate hash')
    specs,audit,ok=_normalize_candidate_runs(strict_json(p)['oracle_definitions']['oracle_a'])
    if not ok: raise ValueError('candidate RunSpec authority')
    return specs,audit

def _reject_constant(value: str) -> None: raise ValueError(f"non-finite JSON value: {value}")
def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
def strict_json_bytes(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
def strict_json(path: Path) -> Any:
    return strict_json_bytes(path.read_bytes())
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

def _identity(st, *, leaf=False):
    return (getattr(st,"st_dev",None),getattr(st,"st_ino",None),stat.S_IFMT(st.st_mode),getattr(st,"st_size",None) if leaf else None,getattr(st,"st_mtime_ns",None),getattr(st,"st_ctime_ns",None),getattr(st,"st_file_attributes",None))
class _FixedReadMissing(Exception): pass
def _safe_production_read(root:Path, requested_path:Path, allowed_relative:str|tuple[str,...], label:str, *, missing_message:str|None=None, lstat_fn=os.lstat, resolve_fn=lambda p:Path(p).resolve(strict=True), open_fn=os.open, fstat_fn=os.fstat, read_fn=os.read, close_fn=os.close)->bytes:
    """Read one fixed production authority file from a verified descriptor."""
    try:
        root=Path(root); candidate=Path(requested_path)
        if not root.is_absolute() or not candidate.is_absolute(): raise FilesystemAuthorizationError(f"{label} lexical authority")
        if type(allowed_relative) is str: allowed=(allowed_relative,)
        elif type(allowed_relative) is tuple and all(type(item) is str for item in allowed_relative): allowed=allowed_relative
        else: raise FilesystemAuthorizationError(f"{label} lexical authority")
        duplicates=[]
        for index,item in enumerate(allowed):
            if item in allowed[:index]: duplicates.append(item)
        if not allowed or duplicates or any(not item or Path(item).is_absolute() or any(part in ("",".","..") for part in Path(item).parts) for item in allowed): raise FilesystemAuthorizationError(f"{label} lexical authority")
        candidates=tuple(root/item for item in allowed)
        equivalent=[]
        for index,authorized in enumerate(candidates):
            if any(authorized==earlier for earlier in candidates[:index]): equivalent.append(index)
        if equivalent: raise FilesystemAuthorizationError(f"{label} lexical authority")
        matches=[]
        for index,authorized in enumerate(candidates):
            if candidate==authorized: matches.append(index)
        if len(matches)!=1: raise FilesystemAuthorizationError(f"{label} lexical authority")
        matched=allowed[matches[0]]
        chain=[root]; current=root
        for part in Path(matched).parts: current=current/part; chain.append(current)
        before=[]
        for index,path in enumerate(chain):
            try: meta=lstat_fn(path)
            except FileNotFoundError:
                if index==len(chain)-1 and type(missing_message) is str and missing_message: raise _FixedReadMissing() from None
                raise FilesystemAuthorizationError(f"{label} path missing") from None
            if stat.S_ISLNK(meta.st_mode) or getattr(meta,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400): raise FilesystemAuthorizationError(f"{label} reparse path")
            if index<len(chain)-1 and not stat.S_ISDIR(meta.st_mode): raise FilesystemAuthorizationError(f"{label} parent is not directory")
            if index==len(chain)-1 and not stat.S_ISREG(meta.st_mode): raise FilesystemAuthorizationError(f"{label} is not a file")
            before.append(_identity(meta,leaf=index==len(chain)-1))
        resolved_root=resolve_fn(root); resolved_candidate=resolve_fn(candidate); resolved_fixed=resolve_fn(root/matched)
        try: resolved_candidate.relative_to(resolved_root)
        except ValueError: raise FilesystemAuthorizationError(f"{label} resolved escape") from None
        if resolved_candidate!=resolved_fixed: raise FilesystemAuthorizationError(f"{label} resolved authority")
        flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0); fd=None
        primary=None
        try:
            try: fd=open_fn(candidate,flags)
            except Exception as exc: raise FilesystemAuthorizationError(f"{label} open failure") from exc
            opened=fstat_fn(fd)
            if not stat.S_ISREG(opened.st_mode) or _identity(opened,leaf=True)!=before[-1]: raise FilesystemAuthorizationError(f"{label} descriptor identity")
            after=[]
            for index,path in enumerate(chain):
                meta=lstat_fn(path)
                if stat.S_ISLNK(meta.st_mode) or getattr(meta,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400) or _identity(meta,leaf=index==len(chain)-1)!=before[index]: raise FilesystemAuthorizationError(f"{label} path changed")
                after.append(meta)
            if resolve_fn(candidate)!=resolved_fixed: raise FilesystemAuthorizationError(f"{label} resolved authority")
            remaining=opened.st_size; chunks=[]
            while remaining:
                chunk=read_fn(fd,remaining)
                if type(chunk) is not bytes or not chunk or len(chunk)>remaining: raise FilesystemAuthorizationError(f"{label} read failure")
                chunks.append(chunk); remaining-=len(chunk)
            if remaining!=0: raise FilesystemAuthorizationError(f"{label} read failure")
            raw=b"".join(chunks); final=fstat_fn(fd)
            if _identity(final,leaf=True)!=_identity(opened,leaf=True) or len(raw)!=opened.st_size: raise FilesystemAuthorizationError(f"{label} file changed")
            for index,path in enumerate(chain):
                meta=lstat_fn(path)
                if stat.S_ISLNK(meta.st_mode) or getattr(meta,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400) or _identity(meta,leaf=index==len(chain)-1)!=before[index]: raise FilesystemAuthorizationError(f"{label} path changed")
            final_root=resolve_fn(root); final_candidate=resolve_fn(candidate)
            try: final_candidate.relative_to(final_root)
            except ValueError: raise FilesystemAuthorizationError(f"{label} resolved escape") from None
            if final_candidate!=resolved_fixed: raise FilesystemAuthorizationError(f"{label} resolved authority")
            return raw
        except BaseException as exc:
            primary=exc; raise
        finally:
            if fd is not None:
                try: close_fn(fd)
                except Exception as exc:
                    if primary is None: raise FilesystemAuthorizationError(f"{label} close failure") from exc
    except _FixedReadMissing:
        if type(missing_message) is str and missing_message: raise RuntimeError(missing_message) from None
        raise FilesystemAuthorizationError(f"{label} path safety") from None
    except FilesystemAuthorizationError: raise
    except Exception as exc: raise FilesystemAuthorizationError(f"{label} path safety") from exc

def _verify_freeze_receipt_at(root: Path) -> dict[str, Any]:
    receipt_path = root / RECEIPT.relative_to(ROOT)
    raw=_safe_production_read(root,receipt_path,RECEIPT.relative_to(ROOT).as_posix(),"freeze receipt",missing_message="freeze receipt hash mismatch")
    if hashlib.sha256(raw).hexdigest().upper() != RECEIPT_SHA256: raise RuntimeError("freeze receipt hash mismatch")
    receipt = strict_json_bytes(raw)
    if not isinstance(receipt,dict) or receipt.get("status") != "FROZEN" or receipt.get("bundle_member_count") != 12: raise RuntimeError("invalid freeze receipt")
    return receipt
def _verify_detached_checksum_at(root: Path) -> str:
    checksum_path = root / CHECKSUM.relative_to(ROOT)
    line=_safe_production_read(root,checksum_path,CHECKSUM.relative_to(ROOT).as_posix(),"detached checksum",missing_message="detached checksum mismatch")
    expected = f"{RECEIPT_SHA256}  protocols/cp10_p0_10_FREEZE_RECEIPT.json\n".encode("ascii")
    if line != expected: raise RuntimeError("detached checksum mismatch")
    return "PASS"
def _verify_bundle_members_at(root: Path, receipt: dict[str,Any]) -> tuple[tuple[str,str],...]:
    verified=[]
    for member in receipt["bundle_members"]:
        path = root / member["path"]
        raw=_safe_production_read(root,path,member["path"],"frozen bundle member",missing_message=f"frozen bundle mismatch: {member['path']}")
        if len(raw) != member["byte_length"] or hashlib.sha256(raw).hexdigest().upper() != member["sha256"]:
            raise RuntimeError(f"frozen bundle mismatch: {member['path']}")
        if member["strict_json_status"] == "PASS": strict_json_bytes(raw)
        verified.append((member["path"],member["sha256"]))
    if len(verified)!=12: raise RuntimeError("invalid frozen bundle member count")
    return tuple(verified)
def verify_frozen_bundle(root: Path = ROOT) -> dict[str, Any]:
    receipt = _verify_freeze_receipt_at(root)
    _verify_detached_checksum_at(root)
    _verify_bundle_members_at(root,receipt)
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
@dataclass(frozen=True)
class RunSpec:
    run_id:str; N:int; dt:float; T:float; step_count:int; role:str; record_times:tuple[float,...]; record_indices:tuple[int,...]
    @classmethod
    def from_json(cls,x):
        keys={"run_id","N","dt","T","step_count","role","record_times","record_indices"}
        if not isinstance(x,dict) or set(x)!=keys: raise ValueError("RunSpec keys")
        if any(isinstance(x[k],bool) or not isinstance(x[k],int) for k in ("N","step_count")) or x["N"]<=0 or x["step_count"]<0: raise ValueError("RunSpec ints")
        if not all(isinstance(x[k],str) and x[k] for k in ("run_id","role")) or not all(isinstance(x[k],(int,float)) and not isinstance(x[k],bool) and np.isfinite(x[k]) and x[k]>0 for k in ("dt","T")): raise ValueError("RunSpec scalars")
        ts,ii=x["record_times"],x["record_indices"]
        if not isinstance(ts,list) or not isinstance(ii,list) or len(ts)!=len(ii) or not ts or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) for v in ts) or any(isinstance(v,bool) or not isinstance(v,int) for v in ii): raise ValueError("RunSpec records")
        if ts[0]!=0 or ii[0]!=0 or ts[-1]!=x["T"] or ii[-1]!=x["step_count"] or any(b<=a for a,b in zip(ts,ts[1:])) or any(b<=a for a,b in zip(ii,ii[1:])) or tuple(ii)!=record_indices(float(x["dt"]),tuple(float(v) for v in ts),x["step_count"]): raise ValueError("RunSpec schedule")
        return cls(x["run_id"],x["N"],float(x["dt"]),float(x["T"]),x["step_count"],x["role"],tuple(float(v) for v in ts),tuple(ii))
    def to_json(self): return {"run_id":self.run_id,"N":self.N,"dt":self.dt,"T":self.T,"step_count":self.step_count,"role":self.role,"record_times":list(self.record_times),"record_indices":list(self.record_indices)}
    def validate(self): return RunSpec.from_json(self.to_json())==self
FROZEN_RUN_SPECS=tuple(RunSpec.from_json({"run_id":i,"N":32,"dt":d,"T":1.0,"step_count":n,"role":r,"record_times":list(RECORD_TIMES),"record_indices":list(record_indices(d,RECORD_TIMES,n))}) for i,d,n,r in RUNS)
FROZEN_SPECS=tuple(x.to_json() for x in FROZEN_RUN_SPECS)

@dataclass(frozen=True)
class _LaunchAuthorityInputs:
    solver_sha256:str; launcher_sha256:str; source_manifest_sha256:str; freeze_receipt_sha256:str; output_root:str; run_specs:tuple[RunSpec,...]
    @property
    def run_ids(self): return tuple(spec.run_id for spec in self.run_specs)
@dataclass(frozen=True)
class _NormalizedLaunchPayload:
    protocol_id:str; status:str; authorization_scope:str; freeze_receipt_sha256:str; solver_sha256:str; launcher_sha256:str; source_manifest_sha256:str; output_root:str; run_ids:tuple[str,...]; run_specs:tuple[RunSpec,...]; execution_id:str; utc_authorization_timestamp:str; oracle_b:bool; scientific_conditions:bool; held_out_access:bool; bootstrap:bool
_LAUNCH_KEYS={"protocol_id","status","authorization_scope","freeze_receipt_sha256","solver_sha256","launcher_sha256","source_manifest_sha256","output_root","run_ids","run_tuples","execution_id","utc_authorization_timestamp","oracle_b","scientific_conditions","held_out_access","bootstrap"}
def _normalize_sha256(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdefABCDEF' for c in value): raise ValueError('sha256')
    return value.upper()
def _validate_execution_id(value):
    if type(value) is not str or not (1<=len(value)<=128) or value!=value.strip() or any(unicodedata.category(char)=='Cc' for char in value): raise ValueError("execution id")
    return value
def _validate_utc_authorization_timestamp(value):
    if type(value) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z',value): raise ValueError("timestamp")
    try:
        parsed=datetime.datetime.fromisoformat(value[:-1]+'+00:00')
        if parsed.tzinfo!=datetime.timezone.utc: raise ValueError
    except (TypeError,ValueError): raise ValueError("timestamp") from None
    return value
def _validate_launch_payload(payload, expected:_LaunchAuthorityInputs)->_NormalizedLaunchPayload:
    if type(expected) is not _LaunchAuthorityInputs:
        raise ValueError('expected authority')
    try:
        eh={k:_normalize_sha256(getattr(expected,k)) for k in ('solver_sha256','launcher_sha256','source_manifest_sha256','freeze_receipt_sha256')}
    except (AttributeError, TypeError, ValueError):
        raise ValueError('expected authority') from None
    if not isinstance(expected.run_specs,tuple) or expected.run_specs!=FROZEN_RUN_SPECS or any(not isinstance(x,RunSpec) for x in expected.run_specs) or eh['freeze_receipt_sha256']!=RECEIPT_SHA256 or expected.output_root!='artifacts/cp10_p0_10_oracle_a/': raise ValueError('expected authority')
    if not isinstance(payload,dict) or any(type(k) is not str for k in payload) or set(payload)!=_LAUNCH_KEYS: raise ValueError("launch schema")
    fixed={"protocol_id":"CP10-P0.10","status":"AUTHORIZED","authorization_scope":"ORACLE_A_THREE_RUN_VERIFICATION_ONLY","output_root":expected.output_root}
    if any(payload[k]!=v for k,v in fixed.items()): raise ValueError("launch fixed values")
    for k in ("freeze_receipt_sha256","solver_sha256","launcher_sha256","source_manifest_sha256"):
        v=payload[k]
        if _normalize_sha256(v)!=eh[k]: raise ValueError("launch hash")
    if any(payload[k] is not False for k in ("oracle_b","scientific_conditions","held_out_access","bootstrap")): raise ValueError("launch scope")
    execution_id=_validate_execution_id(payload['execution_id'])
    ts=_validate_utc_authorization_timestamp(payload['utc_authorization_timestamp'])
    run_ids = payload['run_ids']
    if type(run_ids) is not list or len(run_ids) != 3 or any(type(value) is not str or not value for value in run_ids) or tuple(run_ids) != expected.run_ids:
        raise ValueError('run ids')
    run_tuples = payload['run_tuples']
    required_run_keys = {'run_id','N','dt','T','step_count','role','record_times','record_indices'}
    if type(run_tuples) is not list or len(run_tuples) != 3:
        raise ValueError('run tuples')
    for raw in run_tuples:
        if type(raw) is not dict or any(type(key) is not str for key in raw) or set(raw) != required_run_keys:
            raise ValueError('run tuple schema')
        if type(raw['run_id']) is not str or type(raw['N']) is not int or type(raw['dt']) is not float or not math.isfinite(raw['dt']) or type(raw['T']) is not float or not math.isfinite(raw['T']) or type(raw['step_count']) is not int or type(raw['role']) is not str:
            raise ValueError('run tuple scalars')
        times, indices = raw['record_times'], raw['record_indices']
        if type(times) is not list or len(times) != 21 or any(type(value) is not float or not math.isfinite(value) for value in times) or (times and times[0] == 0.0 and math.copysign(1.0, times[0]) < 0):
            raise ValueError('run tuple times')
        if type(indices) is not list or len(indices) != 21 or any(type(value) is not int for value in indices):
            raise ValueError('run tuple indices')
    try:
        specs=tuple(RunSpec.from_json(raw) for raw in run_tuples)
    except (TypeError,ValueError):
        raise ValueError('run tuples') from None
    if specs!=expected.run_specs or tuple(run_ids) != tuple(spec.run_id for spec in specs): raise ValueError('run authority')
    return _NormalizedLaunchPayload(payload['protocol_id'],payload['status'],payload['authorization_scope'],eh['freeze_receipt_sha256'],eh['solver_sha256'],eh['launcher_sha256'],eh['source_manifest_sha256'],payload['output_root'],tuple(payload['run_ids']),specs,execution_id,ts,False,False,False,False)

@dataclass(frozen=True)
class HashVerificationResult:
    label:str; path:str; sha256:str; status:str
@dataclass(frozen=True)
class SourceManifestAuthorityReport:
    path:str; raw_sha256:str; schema_version:str; solver_sha256:str; runner_sha256:str; launcher_sha256:str; receipt_sha256:str; output_root:str; launch_record_path:str; candidate_targets_sha256:str; complete_targets_sha256:str; filesystem_contract_version:str; status:str
@dataclass(frozen=True)
class PrelaunchAuthorityReport:
    ordered_events:tuple[str,...]
    first_pass_receipt_bundle_result:tuple[tuple[str,str],...]
    solver_hash_result:HashVerificationResult
    launcher_hash_result:HashVerificationResult
    source_manifest_result:SourceManifestAuthorityReport
    filesystem_contract_result:FilesystemPathReport
    launch_record_raw_hash:str
    normalized_launch_authorization:_NormalizedLaunchPayload
    second_pass_revalidation_result:tuple[tuple[str,str],...]
    status:str
class PrelaunchAuthorityStageError(RuntimeError):
    def __init__(self,stage:str,completed_events:tuple[str,...],cause:BaseException):
        self.stage=stage;self.completed_events=tuple(completed_events);self.cause_type=type(cause).__name__
        super().__init__(f"prelaunch authority stage failed: {stage}: {cause}")
@dataclass(frozen=True)
class _PrelaunchCallbacks:
    freeze_receipt:Callable[[],Any]
    detached_checksum:Callable[[],Any]
    bundle_members:Callable[[],Any]
    solver_hash:Callable[[],Any]
    launcher_hash:Callable[[],Any]
    source_manifest:Callable[[],Any]
    filesystem_contract:Callable[[],Any]
    launch_record_path:Callable[[],Any]
    launch_record_hash:Callable[[],Any]
    launch_record_parse:Callable[[],Any]
    launch_payload:Callable[[],Any]
    freeze_receipt_recheck:Callable[[],Any]
    detached_checksum_recheck:Callable[[],Any]
    bundle_members_recheck:Callable[[],Any]
    solver_hash_recheck:Callable[[],Any]
    launcher_hash_recheck:Callable[[],Any]
    source_manifest_recheck:Callable[[],Any]
    filesystem_contract_recheck:Callable[[],Any]

def _authority_immutable(value):
    try:
        if type(value) in (str,int,float,bool,type(None)): return True
        if type(value) is tuple: return all(_authority_immutable(item) for item in value)
        known=(RunSpec,HashVerificationResult,SourceManifestAuthorityReport,FilesystemPathReport,_NormalizedLaunchPayload,PrelaunchAuthorityReport)
        return type(value) in known and all(_authority_immutable(getattr(value,item.name)) for item in fields(value))
    except Exception: return False
def _authority_hash(value): return type(value) is str and len(value)==64 and value==value.upper() and all(c in '0123456789ABCDEF' for c in value)
def _authority_bundle(value):
    return type(value) is tuple and len(value)==12 and all(type(item) is tuple and len(item)==2 and type(item[0]) is str and item[0] and _authority_hash(item[1]) for item in value) and len(tuple(item[0] for item in value))==len(set(item[0] for item in value))
def _authority_hash_result(value,label,path):
    return type(value) is HashVerificationResult and type(value.label) is str and value.label==label and type(value.path) is str and value.path==path and _authority_hash(value.sha256) and type(value.status) is str and value.status=='PASS'
def _authority_source(value,solver,launcher):
    try: return type(value) is SourceManifestAuthorityReport and _authority_hash_result(solver,'solver','fermion/cp10/oracle_a_p0_10.py') and _authority_hash_result(launcher,'launcher','fermion/cp10/oracle_a_launcher_p0_10.py') and _authority_immutable(value) and value.status=='PASS' and value.path==PRODUCTION_SOURCE_MANIFEST_RELATIVE and value.schema_version==PRODUCTION_SOURCE_MANIFEST_SCHEMA and value.output_root==PRODUCTION_OUTPUT_ROOT_RELATIVE+'/' and value.launch_record_path==PRODUCTION_LAUNCH_RECORD_RELATIVE and value.candidate_targets_sha256==PRODUCTION_CANDIDATE_TARGETS_SHA256 and value.complete_targets_sha256==PRODUCTION_TARGETS_SHA256 and value.filesystem_contract_version==FILESYSTEM_CONTRACT_VERSION and value.receipt_sha256==RECEIPT_SHA256 and value.solver_sha256==solver.sha256 and value.runner_sha256==solver.sha256 and value.launcher_sha256==launcher.sha256 and _authority_hash(value.raw_sha256)
    except Exception: return False
def _authority_filesystem(value):
    try: return type(value) is FilesystemPathReport and _authority_immutable(value) and value.project_root==_PRELAUNCH_ROOT_TEXT and value.output_root==_PRELAUNCH_OUTPUT_TEXT and value.targets==PRODUCTION_CANDIDATE_TARGETS and value.target_set_sha256==PRODUCTION_CANDIDATE_TARGETS_SHA256 and value.containment==_PRELAUNCH_CONTAINMENT and value.reparse_findings==() and value.collisions==() and value.reserved_temporary_findings==() and value.status=='PASS'
    except Exception: return False
def _authority_runspec(value):
    try:
        if type(value) is not RunSpec or not _authority_immutable(value) or type(value.run_id) is not str or type(value.N) is not int or type(value.dt) is not float or type(value.T) is not float or type(value.step_count) is not int or type(value.role) is not str or type(value.record_times) is not tuple or type(value.record_indices) is not tuple or any(type(item) is not float or not math.isfinite(item) for item in value.record_times) or any(type(item) is not int or isinstance(item,bool) for item in value.record_indices): return False
        return value.validate() and RunSpec.from_json(value.to_json())==value
    except Exception: return False
def _authority_payload(value,solver,launcher,source):
    if type(value) is not _NormalizedLaunchPayload: return False
    try:
        strings=('protocol_id','status','authorization_scope','freeze_receipt_sha256','solver_sha256','launcher_sha256','source_manifest_sha256','output_root','execution_id','utc_authorization_timestamp')
        _validate_execution_id(value.execution_id); _validate_utc_authorization_timestamp(value.utc_authorization_timestamp)
        return _authority_hash_result(solver,'solver','fermion/cp10/oracle_a_p0_10.py') and _authority_hash_result(launcher,'launcher','fermion/cp10/oracle_a_launcher_p0_10.py') and _authority_source(source,solver,launcher) and _authority_immutable(value) and all(type(getattr(value,name)) is str for name in strings) and value.protocol_id=='CP10-P0.10' and value.status=='AUTHORIZED' and value.authorization_scope=='ORACLE_A_THREE_RUN_VERIFICATION_ONLY' and value.freeze_receipt_sha256==RECEIPT_SHA256 and value.solver_sha256==solver.sha256 and value.launcher_sha256==launcher.sha256 and value.source_manifest_sha256==source.raw_sha256 and value.output_root==PRODUCTION_OUTPUT_ROOT_RELATIVE+'/' and value.run_ids==tuple(spec.run_id for spec in FROZEN_RUN_SPECS) and value.run_specs==FROZEN_RUN_SPECS and all(_authority_runspec(item) for item in value.run_specs) and all(_authority_hash(getattr(value,name)) for name in ('freeze_receipt_sha256','solver_sha256','launcher_sha256','source_manifest_sha256')) and value.oracle_b is False and value.scientific_conditions is False and value.held_out_access is False and value.bootstrap is False
    except Exception: return False
def _validate_authority_results(results):
    bad=lambda: (_ for _ in ()).throw(TypeError('immutable authority results required'))
    if type(results.get('freeze_receipt')) is not str or results['freeze_receipt']!='PASS' or type(results.get('detached_checksum')) is not str or results['detached_checksum']!='PASS' or not _authority_bundle(results.get('bundle_members')): bad()
    solver,launcher=results.get('solver_hash'),results.get('launcher_hash')
    if not _authority_hash_result(solver,'solver','fermion/cp10/oracle_a_p0_10.py') or not _authority_hash_result(launcher,'launcher','fermion/cp10/oracle_a_launcher_p0_10.py'): bad()
    source=results.get('source_manifest')
    if not _authority_source(source,solver,launcher) or not _authority_filesystem(results.get('filesystem_contract')): bad()
    if type(results.get('launch_record_path')) is not str or results['launch_record_path']!=str(ROOT/PRODUCTION_LAUNCH_RECORD_RELATIVE) or not _authority_hash(results.get('launch_record_hash')) or type(results.get('launch_record_parse')) is not str or results['launch_record_parse']!='PASS' or not _authority_payload(results.get('launch_payload'),solver,launcher,source): bad()
    if type(results.get('freeze_receipt_recheck')) is not str or results['freeze_receipt_recheck']!='PASS' or type(results.get('detached_checksum_recheck')) is not str or results['detached_checksum_recheck']!='PASS' or not _authority_bundle(results.get('bundle_members_recheck')): bad()
    solver2,launcher2=results.get('solver_hash_recheck'),results.get('launcher_hash_recheck')
    if not _authority_hash_result(solver2,'solver','fermion/cp10/oracle_a_p0_10.py') or not _authority_hash_result(launcher2,'launcher','fermion/cp10/oracle_a_launcher_p0_10.py') or not _authority_source(results.get('source_manifest_recheck'),solver2,launcher2) or not _authority_filesystem(results.get('filesystem_contract_recheck')): bad()

_SOURCE_MANIFEST_KEYS={"schema_version","protocol_id","status","solver_sha256","runner_sha256","launcher_sha256","freeze_receipt_sha256","output_root","launch_record_path","candidate_targets_sha256","complete_targets_sha256","filesystem_contract_version"}
def _verify_current_hash(label:str,path:Path,expected_sha256:str)->HashVerificationResult:
    try: expected=_normalize_sha256(expected_sha256)
    except ValueError: raise RuntimeError(f"{label} expected hash invalid") from None
    relative=path.relative_to(ROOT).as_posix()
    raw=_safe_production_read(ROOT,path,relative,label,missing_message=f"{label} source missing")
    actual=hashlib.sha256(raw).hexdigest().upper()
    if actual!=expected: raise RuntimeError(f"{label} hash mismatch")
    return HashVerificationResult(label,path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),actual,"PASS")
def _verify_production_source_manifest_at(root:Path,manifest_path:Path,expected_raw_sha256:str)->SourceManifestAuthorityReport:
    fixed=root/PRODUCTION_SOURCE_MANIFEST_RELATIVE
    if Path(manifest_path)!=fixed: raise RuntimeError("source manifest path mismatch")
    try: expected_raw=_normalize_sha256(expected_raw_sha256)
    except ValueError: raise RuntimeError("source manifest expected hash invalid") from None
    raw=_safe_production_read(root,fixed,PRODUCTION_SOURCE_MANIFEST_RELATIVE,"source manifest",missing_message="source manifest missing");actual_raw=hashlib.sha256(raw).hexdigest().upper()
    if actual_raw!=expected_raw: raise RuntimeError("source manifest hash mismatch")
    try: payload=strict_json_bytes(raw)
    except (UnicodeDecodeError,ValueError,TypeError,json.JSONDecodeError) as exc: raise RuntimeError("source manifest parse failure") from exc
    if type(payload) is not dict or set(payload)!=_SOURCE_MANIFEST_KEYS: raise RuntimeError("source manifest schema mismatch")
    solver_raw=_safe_production_read(root,root/"fermion/cp10/oracle_a_p0_10.py","fermion/cp10/oracle_a_p0_10.py","solver",missing_message="solver source missing")
    launcher_raw=_safe_production_read(root,root/"fermion/cp10/oracle_a_launcher_p0_10.py","fermion/cp10/oracle_a_launcher_p0_10.py","launcher",missing_message="launcher source missing")
    solver_hash=hashlib.sha256(solver_raw).hexdigest().upper();launcher_hash=hashlib.sha256(launcher_raw).hexdigest().upper()
    expected={
        "schema_version":PRODUCTION_SOURCE_MANIFEST_SCHEMA,"protocol_id":"CP10-P0.10","status":"AUTHORIZED_FOR_PRELAUNCH",
        "solver_sha256":solver_hash,"runner_sha256":solver_hash,"launcher_sha256":launcher_hash,"freeze_receipt_sha256":RECEIPT_SHA256,
        "output_root":PRODUCTION_OUTPUT_ROOT_RELATIVE+"/","launch_record_path":PRODUCTION_LAUNCH_RECORD_RELATIVE,
        "candidate_targets_sha256":PRODUCTION_CANDIDATE_TARGETS_SHA256,"complete_targets_sha256":PRODUCTION_TARGETS_SHA256,"filesystem_contract_version":FILESYSTEM_CONTRACT_VERSION,
    }
    if payload!=expected: raise RuntimeError("source manifest authority mismatch")
    return SourceManifestAuthorityReport(PRODUCTION_SOURCE_MANIFEST_RELATIVE,actual_raw,payload["schema_version"],solver_hash,solver_hash,launcher_hash,RECEIPT_SHA256,payload["output_root"],payload["launch_record_path"],payload["candidate_targets_sha256"],payload["complete_targets_sha256"],payload["filesystem_contract_version"],"PASS")
def verify_production_source_manifest(expected_source_manifest_sha256:str)->SourceManifestAuthorityReport:
    return _verify_production_source_manifest_at(ROOT,ROOT/PRODUCTION_SOURCE_MANIFEST_RELATIVE,expected_source_manifest_sha256)
def _prelaunch_filesystem_contract_at(root:Path,*,lstat_fn=os.lstat,resolve_fn=lambda p:Path(p).resolve())->FilesystemPathReport:
    return _validate_filesystem_paths(root,PRODUCTION_OUTPUT_ROOT_RELATIVE,PRODUCTION_CANDIDATE_TARGETS,lstat_fn=lstat_fn,resolve_fn=resolve_fn)
def _fixed_launch_record_path_at(root:Path,record_path:Path,*,lstat_fn=os.lstat,resolve_fn=lambda p:Path(p).resolve())->Path:
    fixed=root/PRODUCTION_LAUNCH_RECORD_RELATIVE
    if Path(record_path)!=fixed: raise FilesystemAuthorizationError("launch record path override")
    try: metadata=lstat_fn(fixed)
    except FileNotFoundError: raise RuntimeError("launch record missing") from None
    except OSError as exc: raise FilesystemAuthorizationError("launch record inspection") from exc
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata,"st_file_attributes",0)&0x400: raise FilesystemAuthorizationError("launch record reparse")
    if not stat.S_ISREG(metadata.st_mode): raise FilesystemAuthorizationError("launch record is not a file")
    try:
        resolved_root=resolve_fn(root);resolved_output=resolve_fn(root/PRODUCTION_OUTPUT_ROOT_RELATIVE);resolved_record=resolve_fn(fixed)
        resolved_output.relative_to(resolved_root);resolved_record.relative_to(resolved_root);resolved_record.relative_to(resolved_output)
    except (OSError,ValueError) as exc: raise FilesystemAuthorizationError("launch record resolved escape") from exc
    return fixed
def _launch_record_raw_at(path:Path,expected_launch_record_sha256:str,*,root:Path=ROOT,**read_callbacks)->tuple[bytes,str]:
    try: expected=_normalize_sha256(expected_launch_record_sha256)
    except ValueError: raise RuntimeError("launch record expected hash invalid") from None
    raw=_safe_production_read(root,path,PRODUCTION_LAUNCH_RECORD_RELATIVE,"launch record",missing_message="launch record missing",**read_callbacks)
    actual=hashlib.sha256(raw).hexdigest().upper()
    if actual!=expected: raise RuntimeError("launch record hash mismatch")
    return raw,actual
def _launch_record_payload(raw:bytes)->dict[str,Any]:
    try: payload=strict_json_bytes(raw)
    except (UnicodeDecodeError,ValueError,TypeError,json.JSONDecodeError) as exc: raise RuntimeError("launch record parse failure") from exc
    if type(payload) is not dict: raise RuntimeError("launch record parse failure")
    return payload
def _validate_launch_record_at(root:Path,record_path:Path,expected_launch_record_sha256:str,expected_authority:_LaunchAuthorityInputs,*,lstat_fn=os.lstat,resolve_fn=lambda p:Path(p).resolve())->_NormalizedLaunchPayload:
    fixed=_fixed_launch_record_path_at(root,record_path,lstat_fn=lstat_fn,resolve_fn=resolve_fn)
    _prelaunch_filesystem_contract_at(root,lstat_fn=lstat_fn,resolve_fn=resolve_fn)
    raw,_actual=_launch_record_raw_at(fixed,expected_launch_record_sha256,root=root,lstat_fn=lstat_fn,resolve_fn=resolve_fn)
    payload=_launch_record_payload(raw)
    try: return _validate_launch_payload(payload,expected_authority)
    except (TypeError,ValueError) as exc: raise RuntimeError("launch payload invalid") from exc
def validate_launch_record(expected_launch_record_sha256:str,expected_authority:_LaunchAuthorityInputs)->_NormalizedLaunchPayload:
    return _validate_launch_record_at(ROOT,ROOT/PRODUCTION_LAUNCH_RECORD_RELATIVE,expected_launch_record_sha256,expected_authority)

def _prelaunch_authority_engine(callbacks:_PrelaunchCallbacks)->PrelaunchAuthorityReport:
    if type(callbacks) is not _PrelaunchCallbacks: raise TypeError("prelaunch callbacks required")
    completed=[];results={}
    def perform(stage):
        try: value=getattr(callbacks,stage)()
        except BaseException as exc: raise PrelaunchAuthorityStageError(stage,tuple(completed),exc) from exc
        completed.append(stage);results[stage]=value;return value
    for stage in PRELAUNCH_AUTHORITY_EVENTS[:-1]: perform(stage)
    try:
        _validate_authority_results(results)
        source_result=results["source_manifest"];filesystem_result=results["filesystem_contract"];authorization=results["launch_payload"]
        if results["freeze_receipt_recheck"]!=results["freeze_receipt"] or results["detached_checksum_recheck"]!=results["detached_checksum"] or results["bundle_members_recheck"]!=results["bundle_members"] or results["solver_hash_recheck"]!=results["solver_hash"] or results["launcher_hash_recheck"]!=results["launcher_hash"] or results["source_manifest_recheck"]!=source_result or results["filesystem_contract_recheck"]!=filesystem_result: raise RuntimeError("second-pass authority changed")
        first=(("freeze_receipt",results["freeze_receipt"]),("detached_checksum",results["detached_checksum"]),*results["bundle_members"])
        second=(("freeze_receipt",results["freeze_receipt_recheck"]),("detached_checksum",results["detached_checksum_recheck"]),*results["bundle_members_recheck"],("solver_hash",results["solver_hash_recheck"].sha256),("launcher_hash",results["launcher_hash_recheck"].sha256),("source_manifest",results["source_manifest_recheck"].raw_sha256),("filesystem_contract",results["filesystem_contract_recheck"].target_set_sha256))
        report=PrelaunchAuthorityReport(tuple(completed)+( "authorized_pre_core",),first,results["solver_hash"],results["launcher_hash"],source_result,filesystem_result,results["launch_record_hash"],authorization,second,"AUTHORIZED_PRE_CORE")
        if not _authority_immutable(report): raise TypeError("immutable authority results required")
    except PrelaunchAuthorityStageError: raise
    except Exception as exc: raise PrelaunchAuthorityStageError("authorized_pre_core",tuple(completed),exc) from exc
    completed.append("authorized_pre_core")
    return report
def production_prelaunch_authority(expected_launch_record_sha256:str,expected_authority:_LaunchAuthorityInputs,expected_source_manifest_sha256:str)->PrelaunchAuthorityReport:
    state={}
    def receipt(key): state[key]=_verify_freeze_receipt_at(ROOT);return "PASS"
    def checksum(): return _verify_detached_checksum_at(ROOT)
    def members(key): return _verify_bundle_members_at(ROOT,state[key])
    def solver(): return _verify_current_hash("solver",ROOT/"fermion/cp10/oracle_a_p0_10.py",expected_authority.solver_sha256)
    def launcher(): return _verify_current_hash("launcher",ROOT/"fermion/cp10/oracle_a_launcher_p0_10.py",expected_authority.launcher_sha256)
    def source():
        try:
            if _normalize_sha256(expected_source_manifest_sha256)!=_normalize_sha256(expected_authority.source_manifest_sha256): raise RuntimeError("source manifest authority hash mismatch")
        except (AttributeError,TypeError,ValueError): raise RuntimeError("source manifest authority hash mismatch") from None
        return _verify_production_source_manifest_at(ROOT,ROOT/PRODUCTION_SOURCE_MANIFEST_RELATIVE,expected_source_manifest_sha256)
    def filesystem(): return _prelaunch_filesystem_contract_at(ROOT)
    def record_path(): state["record_path"]=_fixed_launch_record_path_at(ROOT,ROOT/PRODUCTION_LAUNCH_RECORD_RELATIVE);return str(state["record_path"])
    def record_hash(): state["record_raw"],state["record_hash"]=_launch_record_raw_at(state["record_path"],expected_launch_record_sha256);return state["record_hash"]
    def record_parse(): state["record_payload"]=_launch_record_payload(state["record_raw"]);return "PASS"
    def launch_payload():
        try: state["authorization"]=_validate_launch_payload(state["record_payload"],expected_authority)
        except (TypeError,ValueError) as exc: raise RuntimeError("launch payload invalid") from exc
        return state["authorization"]
    callbacks=_PrelaunchCallbacks(lambda:receipt("receipt_first"),checksum,lambda:members("receipt_first"),solver,launcher,source,filesystem,record_path,record_hash,record_parse,launch_payload,lambda:receipt("receipt_second"),checksum,lambda:members("receipt_second"),solver,launcher,source,filesystem)
    return _prelaunch_authority_engine(callbacks)

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
def _integrate_frozen(spec, initial, authorization):
    if not isinstance(authorization,_FrozenAuthorization) or authorization.receipt_hash!=RECEIPT_SHA256 or authorization.source_hash!=sha256(ROOT/"artifacts/cp10_p0_10_oracle_a/source_manifest.json") or authorization.tuples!=frozen_json_specs() or authorization.output_root!="artifacts/cp10_p0_10_oracle_a/": raise PermissionError("invalid frozen capability")
    if not isinstance(spec,RunSpec) or spec not in FROZEN_RUN_SPECS: raise PermissionError("wrong frozen spec")
    return _integrate_core(spec,initial)
def validate_completed_run(run, initial):
    required={"spectral","physical","exact_spectral","exact_physical","metrics"}
    if required-set(run) or any(np.asarray(run[k]).shape!=(21,32,32) for k in required-{"metrics"}): raise RuntimeError("incomplete run arrays")
    m=run["metrics"]
    if any(m[k] is None for k in ("final_relative_l2","trajectory_relative_l2","modal_max","zero_mode_error","nyquist_max","correction_max","nonfinite_count")): raise RuntimeError("dropped metric")
    if not np.isfinite(run["spectral"]).all() or m["nyquist_max"]!=0 or m["correction_max"]>1e-13: raise RuntimeError("hard stop")
    if not np.array_equal(run["spectral"][0],initial): raise RuntimeError("fixture identity")
    return True
def _integrate_core(spec: RunSpec, initial: np.ndarray) -> dict[str,Any]:
    """Numerical core only: no authorization and no writing."""
    if not isinstance(spec,RunSpec): raise TypeError("validated RunSpec required")
    state=np.array(initial,dtype="<c16",copy=True); records=[state.copy()]; corrections=[]; schedule=spec.record_indices
    for step in range(1,spec.step_count+1):
        state,corr=imex_step(state,spec.dt,initial[0,0]); corrections.append(corr)
        if step in schedule: records.append(state.copy())
    if len(records)!=len(schedule) or not np.isfinite(state).all(): raise RuntimeError("record or finite failure")
    spectral=np.asarray(records,dtype="<c16"); physical=np.asarray([np.real(np.fft.ifft2(x)*spec.N**2) for x in spectral],dtype="<f8"); exact=np.asarray([analytic(initial,t) for t in spec.record_times],dtype="<c16")
    return {"spectral":spectral,"physical":physical,"exact_spectral":exact,"exact_physical":np.asarray([np.real(np.fft.ifft2(x)*spec.N**2) for x in exact],dtype="<f8"),"corrections":corrections}
def integrate_synthetic(spec: dict[str,Any], initial: np.ndarray) -> dict[str,Any]:
    spec=RunSpec.from_json(spec)
    if spec.run_id in {x.run_id for x in FROZEN_RUN_SPECS}: raise PermissionError("frozen specification integration requires launch record")
    if spec.N>8 or spec.step_count>4: raise ValueError("synthetic integration limits")
    return _integrate_core(spec,initial)
def run_metrics(result:dict[str,Any]) -> dict[str,Any]:
    n,e=result["spectral"],result["exact_spectral"]; p,ep=result["physical"],result["exact_physical"]; keep=retained_mask(n.shape[-1])
    return {"final_relative_l2":relative_final(p[-1],ep[-1]),"trajectory_relative_l2":relative_trajectory(p,ep),"modal_max":relative_modal_max(n[:,keep],e[:,keep]),"zero_mode_error":float(np.max(abs(n[:,0,0]-e[:,0,0]))),"nyquist_max":float(max(abs(n[:,:,n.shape[-1]//2]).max(),abs(n[:,n.shape[-1]//2,:]).max())),"correction_max":max(result["corrections"],default=0.0),"nonfinite_count":int(n.size-np.isfinite(n).sum()),"step_count":len(result["corrections"]),"record_count":len(n)}
def aggregate(fine,medium_fine_metrics,all_ids,coarse_present=True):
    return coarse_present and all_ids==[x.run_id for x in FROZEN_RUN_SPECS] and fine["final_relative_l2"]<=.02 and fine["trajectory_relative_l2"]<=.02 and fine["modal_max"]<=.02 and medium_fine_metrics["final"]<=.02 and medium_fine_metrics["trajectory"]<=.02 and fine["zero_mode_error"]<=1e-12 and fine["nyquist_max"]==0 and fine["correction_max"]<=1e-13 and fine["nonfinite_count"]==0
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
    raise PermissionError("Oracle-A execution remains unauthorized")
