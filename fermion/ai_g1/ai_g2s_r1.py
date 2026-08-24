"""AI-G2S-R1.1 execution infrastructure.

This module intentionally does not expose a full-benchmark command.  It
provides the deterministic, test-isolated primitives which must pass R1.1
before P1.1 final evaluation can be authorized.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
from torch import Tensor, nn
from torch.nn import functional as F


P10_SHA256 = "8F458D3CA9822897A7FBB7FF92314E312B37E9DF11E113E102D58DF71EACB8AD"
P11_SHA256 = "BBDAB6671494069BBA94D9E2D0382D9A91896C634BEB83A315E7936FC961B03C"
RUNNER_SOURCE_RELATIVE_PATHS = (
    "fermion/ai_g1/ai_g2s_r1.py",
    "fermion/ai_g1/ai_g2s.py",
    "fermion/ai_g1/spectral.py",
    "fermion/ai_g1/diagnostics.py",
    "fermion/hr/reference_193.py",
)


class ProtocolFailure(RuntimeError): pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical_json_sha256(path: Path) -> str:
    """Optional semantic JSON digest; never substitutes for a raw digest."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolFailure(f"invalid JSON artifact: {path}") from error
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest().upper()


def verify_json_content(path: Path, *, raw_sha256: str, canonical_json_sha256_expected: str | None = None) -> dict[str, str]:
    """Verify byte provenance first; canonical JSON is an explicitly optional extra."""
    actual_raw = sha256(path)
    if actual_raw != raw_sha256.upper():
        raise ProtocolFailure(f"raw SHA-256 mismatch: {path}")
    result = {"raw_sha256": actual_raw}
    if canonical_json_sha256_expected is not None:
        actual_canonical = canonical_json_sha256(path)
        if actual_canonical != canonical_json_sha256_expected.upper():
            raise ProtocolFailure(f"canonical JSON SHA-256 mismatch: {path}")
        result["canonical_json_sha256"] = actual_canonical
    return result


def load_frozen_protocol(root: Path) -> dict[str, Any]:
    p10, p11 = root / "configs" / "ai_g2s_p1_0.json", root / "configs" / "ai_g2s_p1_1.json"
    if sha256(p10) != P10_SHA256 or sha256(p11) != P11_SHA256:
        raise ProtocolFailure("authoritative AI-G2S configuration hash mismatch")
    cfg = json.loads(p11.read_text(encoding="utf-8"))
    if cfg.get("parent_config_sha256") != P10_SHA256 or cfg.get("protocol_id") != "AI-G2S-P1.1":
        raise ProtocolFailure("P1.1 parent/protocol declaration mismatch")
    return cfg


def canonical_source_manifest(root: Path, paths: Iterable[Path]) -> dict[str, Any]:
    entries = []
    for path in sorted({item.resolve() for item in paths}, key=lambda item: item.as_posix().lower()):
        if not path.is_file(): raise ProtocolFailure(f"manifest source missing: {path}")
        entries.append({"path": path.relative_to(root.resolve()).as_posix(), "sha256": sha256(path)})
    canonical = "".join(f"{item['sha256'].lower()}  {item['path']}\n" for item in entries).encode()
    return {"format": "sha256-two-space-relative-path-v1", "entries": entries,
            "tree_sha256": hashlib.sha256(canonical).hexdigest().upper()}


def verify_source_manifest(root: Path, manifest_path: Path, *, manifest_raw_sha256: str) -> dict[str, Any]:
    """Byte-verify the manifest then every declared, fixed source member."""
    verify_json_content(manifest_path, raw_sha256=manifest_raw_sha256)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ProtocolFailure("source manifest entries missing")
    observed = {str(entry.get("path")) for entry in entries}
    expected = set(RUNNER_SOURCE_RELATIVE_PATHS)
    if observed != expected or len(entries) != len(expected):
        raise ProtocolFailure("source-manifest source-set addition, omission, or duplicate")
    recalculated = canonical_source_manifest(root, [root / item for item in RUNNER_SOURCE_RELATIVE_PATHS])
    if recalculated["tree_sha256"] != str(manifest.get("tree_sha256", "")).upper():
        raise ProtocolFailure("source manifest tree digest mismatch")
    declared = {entry["path"]: str(entry.get("sha256", "")).upper() for entry in entries}
    for relative in RUNNER_SOURCE_RELATIVE_PATHS:
        if sha256(root / relative) != declared.get(relative):
            raise ProtocolFailure(f"source hash mismatch: {relative}")
    return {"manifest_raw_sha256": sha256(manifest_path), "tree_sha256": recalculated["tree_sha256"], "verified_entries": len(entries)}


def environment_manifest() -> dict[str, Any]:
    return {"python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__,
            "os": platform.platform(), "cuda_available": torch.cuda.is_available(),
            "deterministic_algorithms_current": torch.are_deterministic_algorithms_enabled(),
            "deterministic_algorithms_enforced_by_full_runner": True,
            "git_head": None, "git_state": "repository_not_initialized"}


@dataclass(frozen=True)
class SplitData:
    task: str; split: str; x: Tensor; y: Tensor; metadata: dict[str, Any]


class FinalTestAccessGate:
    """Forbid final-test material until all validation selections are registered."""
    def __init__(self) -> None: self._selected: set[tuple[str, str, int]] = set()
    def select(self, task: str, model: str, seed: int) -> None: self._selected.add((task, model, seed))
    def require(self, task: str, model: str, seed: int) -> None:
        if (task, model, seed) not in self._selected:
            raise ProtocolFailure("test-loader access before validation checkpoint selection")


class DeterministicSplitFactory:
    """P1.1 split generator. Test data needs an explicit gate and model identity."""
    def __init__(self, config: dict[str, Any]) -> None: self.config = config
    def _rng(self, task: str, split: str) -> np.random.Generator:
        try: seed = self.config["dataset_rng"]["seeds"][task][split]
        except KeyError as error: raise ProtocolFailure(f"no frozen seed for {task}.{split}") from error
        return np.random.Generator(np.random.PCG64DXSM(seed))
    def count(self, task: str, split: str) -> int:
        key = {"test_id": "test_id", "test_ood": "test_ood"}.get(split, split)
        try: return int(self.config["datasets"][task][key])
        except KeyError as error: raise ProtocolFailure(f"no frozen cardinality for {task}.{split}") from error
    def generate(self, task: str, split: str, *, limit: int | None = None,
                 gate: FinalTestAccessGate | None = None, model: str | None = None,
                 training_seed: int | None = None, resolution: int | None = None) -> SplitData:
        if split.startswith("test"):
            if gate is None or model is None or training_seed is None: raise ProtocolFailure("test split needs a selected condition")
            gate.require(task, model, training_seed)
        source_task = "elliptic_poisson_darcy" if task == "coordinate_permutation" else task
        count = min(self.count(source_task, split), limit) if limit is not None else self.count(source_task, split)
        rng = self._rng(source_task, split)
        ood = split == "test_ood"
        if task == "coordinate_permutation":
            base = self._elliptic(split, count, rng, ood)
            order = np.random.Generator(np.random.PCG64DXSM(self.config["dataset_rng"]["coordinate_permutation_seed"])).permutation(32 * 32)
            x = base.x.reshape(count, 2, -1)[:, :, order].reshape_as(base.x)
            y = base.y.reshape(count, 1, -1)[:, :, order].reshape_as(base.y)
            return SplitData(task, split, x, y, {**base.metadata, "permutation_seed": 25001})
        if task == "elliptic_poisson_darcy": return self._elliptic(split, count, rng, ood)
        if task == "cross_resolution_fields": return self._cross(split, count, rng, ood, resolution=resolution or 32)
        if task == "multiscale_forecasting": return self._forecast(split, count, rng, ood)
        if task == "tabular_control": return self._tabular(split, count, rng)
        raise ProtocolFailure(f"unknown task: {task}")
    @staticmethod
    def _colored(rng: np.random.Generator, n: int, length: float, amplitude: float) -> np.ndarray:
        k = np.fft.fftfreq(n, d=1 / n); ky, kx = np.meshgrid(k, k, indexing="ij"); k2 = kx*kx + ky*ky
        coeff = rng.normal(size=(n,n)) + 1j*rng.normal(size=(n,n)); coeff[0,0] = 0
        field = np.fft.ifft2(coeff / (1 + (2*np.pi*length)**2*k2)**1.25).real; field /= max(field.std(), 1e-12)
        return amplitude * field
    @staticmethod
    def _apply_operator(u: np.ndarray, kappa: np.ndarray) -> np.ndarray:
        h = 1.0 / u.shape[0]; xp, xm = np.roll(u, -1, 1), np.roll(u, 1, 1); yp, ym = np.roll(u, -1, 0), np.roll(u, 1, 0)
        kxp = 2*kappa*np.roll(kappa,-1,1)/(kappa+np.roll(kappa,-1,1)); kxm = 2*kappa*np.roll(kappa,1,1)/(kappa+np.roll(kappa,1,1))
        kyp = 2*kappa*np.roll(kappa,-1,0)/(kappa+np.roll(kappa,-1,0)); kym = 2*kappa*np.roll(kappa,1,0)/(kappa+np.roll(kappa,1,0))
        return (kxp*(u-xp)+kxm*(u-xm)+kyp*(u-yp)+kym*(u-ym))/(h*h) + .1*u
    @classmethod
    def _cg(cls, kappa: np.ndarray, forcing: np.ndarray, *, rtol: float, maxiter: int) -> tuple[np.ndarray, float, int]:
        x=np.zeros_like(forcing); r=forcing-cls._apply_operator(x,kappa); p=r.copy(); rs=float(np.vdot(r,r)); initial=max(rs**.5,1e-300)
        for iteration in range(1,maxiter+1):
            ap=cls._apply_operator(p,kappa); denom=float(np.vdot(p,ap))
            if not np.isfinite(denom) or denom<=0: raise ProtocolFailure("elliptic CG breakdown")
            alpha=rs/denom; x=x+alpha*p; r=r-alpha*ap; new=float(np.vdot(r,r))
            if new**.5 <= rtol*initial: return x,float(new**.5),iteration
            p=r+(new/rs)*p; rs=new
        raise ProtocolFailure("elliptic CG non-convergence")
    def _elliptic(self, split: str, count: int, rng: np.random.Generator, ood: bool) -> SplitData:
        bounds = self.config["tasks"]["elliptic_poisson_darcy"]["ood" if ood else "id_and_calibration"]; n=32; xs=[]; ys=[]; residuals=[]
        for _ in range(count):
            pl=rng.uniform(*bounds["permeability_length_uniform"]); pa=rng.uniform(*bounds["log_permeability_amplitude_uniform"]); fl=rng.uniform(*bounds["forcing_length_uniform"])
            logk=self._colored(rng,n,pl,pa); k=np.exp(logk); f=self._colored(rng,n,fl,1.0); u,residual,_=self._cg(k,f,rtol=1e-10,maxiter=5000)
            if not np.isfinite(residual) or residual > 1e-10*max(np.linalg.norm(f),1e-300): raise ProtocolFailure("elliptic residual/solver-convergence failure")
            xs.append(np.stack((logk,f))); ys.append(u[None]); residuals.append(float(residual))
        return SplitData("elliptic_poisson_darcy", split, torch.tensor(np.array(xs),dtype=torch.float32), torch.tensor(np.array(ys),dtype=torch.float32), {"pde_residual_max":max(residuals),"solver_converged":True})
    def _cross(self, split: str, count: int, rng: np.random.Generator, ood: bool, *, resolution: int) -> SplitData:
        if resolution not in (32, 64, 128): raise ProtocolFailure("unfrozen cross-resolution render")
        n=resolution; x=[]; y=[]; max_mode=16 if ood else 8
        yy,xx=np.meshgrid(np.arange(n)/n,np.arange(n)/n,indexing="ij")
        for _ in range(count):
            field=np.zeros((n,n));
            for _mode in range(12):
                a,b=rng.integers(-max_mode,max_mode+1,2); a = a or 1; b = b or 1; field += rng.normal()*np.cos(2*np.pi*(a*xx+b*yy))
            field/=max(field.std(),1e-12); target=np.tanh(field)+.25*(field*field-field.mean())
            x.append(field[None]); y.append(target[None])
        return SplitData("cross_resolution_fields",split,torch.tensor(np.array(x),dtype=torch.float32),torch.tensor(np.array(y),dtype=torch.float32),{"resolution":[n,n],"ood":ood})
    def _forecast(self, split: str, count: int, rng: np.random.Generator, ood: bool) -> SplitData:
        freqs=self.config["tasks"]["multiscale_forecasting"]["ood_frequencies_uniform" if ood else "id_frequencies_uniform"]; mod=self.config["tasks"]["multiscale_forecasting"]["ood_modulation_uniform" if ood else "id_modulation_uniform"]; t=np.arange(160); xs=[]; ys=[]
        for _ in range(count):
            signal=np.zeros((3,160));
            for c in range(3):
                for lo,hi in freqs:
                    f=rng.uniform(lo,hi); signal[c]+=rng.uniform(.4,1.0)*(1+rng.uniform(*mod)*t)*np.sin(2*np.pi*f*t+rng.uniform(0,2*np.pi))
                noise=np.zeros(160)
                for i in range(1,160): noise[i]=.6*noise[i-1]+rng.normal(0,.05)
                signal[c]+=noise
            xs.append(signal[:,:128]); ys.append(signal[:,128:])
        return SplitData("multiscale_forecasting",split,torch.tensor(np.array(xs),dtype=torch.float32),torch.tensor(np.array(ys),dtype=torch.float32),{"windows_per_trajectory":1,"ood":ood})
    def _tabular(self, split: str, count: int, rng: np.random.Generator) -> SplitData:
        i=np.arange(64); cov=.5**np.abs(i[:,None]-i[None,:]); x=rng.multivariate_normal(np.zeros(64),cov,size=count); perm=np.random.Generator(np.random.PCG64DXSM(25001)).permutation(64); x=x[:,perm]; y=.7*x[:,0]*x[:,1]+np.sin(x[:,2])+.3*x[:,3]**2-.5*x[:,4]+.2*x[:,5]*x[:,6]*x[:,7]+.1*rng.normal(size=count)
        return SplitData("tabular_control",split,torch.tensor(x.reshape(count,1,8,8),dtype=torch.float32),torch.tensor(y[:,None],dtype=torch.float32),{"feature_permutation_seed":25001})


class _Residual(nn.Module):
    def __init__(self, width:int, dimension:int, kernel:int=1) -> None:
        super().__init__(); conv=nn.Conv1d if dimension==1 else nn.Conv2d; pad=kernel//2
        self.a,self.b,self.c=conv(width,width,kernel,padding=pad),conv(width,width,kernel,padding=pad),conv(width,width,kernel,padding=pad)
    def forward(self,x:Tensor)->Tensor: return x+ self.c(F.gelu(self.b(F.gelu(self.a(x)))))


class CapacityModel(nn.Module):
    def __init__(self, kind:str, width:int, dimension:int, in_channels:int, out_channels:int, scalar:bool=False) -> None:
        super().__init__(); self.kind,self.dimension,self.scalar=kind,dimension,scalar; conv=nn.Conv1d if dimension==1 else nn.Conv2d; kernel=3 if kind=="fully_convolutional_cnn" else 1
        self.input=conv(in_channels,width,kernel,padding=kernel//2); blocks={"spectral":6,"spectral_ablation":6,"mlp_shared_point_patch":8,"fully_convolutional_cnn":8,"fourier_neural_operator":4}.get(kind,4)
        per=2 if kind in {"mlp_shared_point_patch","fully_convolutional_cnn"} else (4 if kind=="fourier_neural_operator" else 3)
        self.blocks=nn.ModuleList([_Residual(width,dimension,kernel) for _ in range(blocks*per)])
        self.output=conv(width,out_channels,kernel,padding=kernel//2); self.gate=nn.Parameter(torch.zeros(())) if kind=="spectral" else None
    def forward(self,x:Tensor)->Tensor:
        z=self.input(x)
        for block in self.blocks: z=block(z)
        if self.gate is not None: z=z*(1+torch.tanh(self.gate))
        y=self.output(z)
        if self.scalar: return y.mean(tuple(range(2,y.ndim)))
        return y


class TransformerCapacityModel(nn.Module):
    """Four-layer, four-head patch transformer with normalized-grid-free positions."""
    def __init__(self,width:int,dimension:int,in_channels:int,out_channels:int,scalar:bool=False)->None:
        super().__init__(); self.dimension,self.scalar,self.out_channels=dimension,scalar,out_channels; self.patch=4
        conv=nn.Conv1d if dimension==1 else nn.Conv2d; self.embed=conv(in_channels,width,self.patch,stride=self.patch)
        layer=nn.TransformerEncoderLayer(width,4,dim_feedforward=4*width,batch_first=True,dropout=0.0,activation="gelu")
        self.encoder=nn.TransformerEncoder(layer,4); self.decode=nn.Linear(width,out_channels*(self.patch**dimension))
    def forward(self,x:Tensor)->Tensor:
        spatial=x.shape[2:]; z=self.embed(x)
        if self.dimension==1:
            n,w,l=z.shape; tokens=self.encoder(z.transpose(1,2)); y=self.decode(tokens).reshape(n,l,self.out_channels,self.patch).permute(0,2,1,3).reshape(n,self.out_channels,l*self.patch)
            y=F.interpolate(y,size=spatial,mode="linear",align_corners=False)
        else:
            n,w,h,l=z.shape; tokens=self.encoder(z.flatten(2).transpose(1,2)); y=self.decode(tokens).reshape(n,h,l,self.out_channels,self.patch,self.patch).permute(0,3,1,4,2,5).reshape(n,self.out_channels,h*self.patch,l*self.patch)
            y=F.interpolate(y,size=spatial,mode="bilinear",align_corners=False)
        return y.mean(tuple(range(2,y.ndim))) if self.scalar else y


def parameter_count(model:nn.Module)->int: return sum(item.numel() for item in model.parameters() if item.requires_grad)


_WIDTH_CACHE: dict[tuple[str,int,int,int,bool], int] = {}

def build_capacity_model(kind:str, *, dimension:int, in_channels:int, out_channels:int, scalar:bool=False, config:dict[str,Any]) -> nn.Module:
    contract=config["model_capacity_contract"]; target=int(contract["target_trainable_parameters"]); tolerance=float(contract["tolerance_fraction"])
    key=(kind,dimension,in_channels,out_channels,scalar)
    maker=(lambda width: TransformerCapacityModel(width,dimension,in_channels,out_channels,scalar)) if kind=="transformer_patch_sinusoidal" else (lambda width: CapacityModel(kind,width,dimension,in_channels,out_channels,scalar))
    widths=range(16,193,4) if kind=="transformer_patch_sinusoidal" else range(16,193)
    if key in _WIDTH_CACHE: return maker(_WIDTH_CACHE[key])
    choices=[(width,maker(width)) for width in widths]
    valid=[item for item in choices if abs(parameter_count(item[1])-target)/target<=tolerance]
    if not valid: raise ProtocolFailure(f"no capacity-valid width for {kind}")
    width,model=min(valid,key=lambda item:(abs(parameter_count(item[1])-target),item[0]))
    _WIDTH_CACHE[key]=width
    return model


def normalized_mse(prediction:Tensor,target:Tensor,mean:Tensor,std:Tensor)->Tensor:
    if torch.any(std < 1e-6): raise ProtocolFailure("normalization SD floor violation")
    value=((prediction-target)/std).square()
    return value.flatten(1).mean(1)


def deterministic_hierarchical_bootstrap(spectral:np.ndarray, ablation:np.ndarray, *, seed:int=20260822,resamples:int=10000)->tuple[float,float,float]:
    if spectral.shape!=ablation.shape or spectral.ndim!=2 or spectral.shape[0]!=3: raise ProtocolFailure("paired bootstrap requires [3 seeds, realizations] matched losses")
    if not (np.isfinite(spectral).all() and np.isfinite(ablation).all()): raise ProtocolFailure("non-finite loss in bootstrap")
    rng=np.random.Generator(np.random.PCG64DXSM(seed)); values=[]; n=spectral.shape[1]
    for _ in range(resamples):
        seeds=rng.integers(0,3,3); realizations=rng.integers(0,n,(3,n)); s=np.mean([spectral[k,realizations[j]].mean() for j,k in enumerate(seeds)]); a=np.mean([ablation[k,realizations[j]].mean() for j,k in enumerate(seeds)]); values.append(1-s/a)
    array=np.asarray(values); return float(array.mean()),float(np.quantile(array,.025)),float(np.quantile(array,.975))


def finalize_condition_records(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Validate complete selected-condition records before any gate statistic.

    This finalizer consumes already-evaluated values only; it has no dataset
    loader and therefore cannot bypass :class:`FinalTestAccessGate`.
    """
    tasks=("elliptic_poisson_darcy","cross_resolution_fields","multiscale_forecasting","coordinate_permutation","tabular_control")
    expected={f"{task}:{model}:{seed}" for task in tasks for model in config["models"] for seed in config["training_seeds"]}
    observed={str(item.get("condition_id")) for item in records}
    missing=sorted(expected-observed); unexpected=sorted(observed-expected)
    if missing or unexpected: raise ProtocolFailure(f"missing/unknown conditions: missing={missing}, unknown={unexpected}")
    for item in records:
        value=item.get("normalized_loss")
        if not isinstance(value,(int,float)) or not np.isfinite(value): raise ProtocolFailure(f"non-finite final loss: {item.get('condition_id')}")
    return {"condition_count":len(records),"complete":True,"gate_verdict":"NOT_COMPUTED"}


def parseval_audit(field: Tensor) -> dict[str, float]:
    """Parseval check using orthonormal FFT normalization."""
    spectrum=torch.fft.fftn(field,dim=tuple(range(-2,0)),norm="ortho")
    spatial=float(field.square().mean().detach()); spectral=float(spectrum.abs().square().mean().detach())
    return {"spatial_power":spatial,"spectral_power":spectral,"absolute_error":abs(spatial-spectral)}


def radial_frequency_bins(height:int,width:int,*,bins:int=16) -> dict[str, Any]:
    if height<2 or width<2 or bins<1: raise ProtocolFailure("invalid frequency-bin dimensions")
    ky=torch.fft.fftfreq(height,d=1/height)*2*torch.pi; kx=torch.fft.fftfreq(width,d=1/width)*2*torch.pi
    radius=torch.sqrt(ky[:,None].square()+kx[None,:].square()); cutoff=torch.pi*min(height,width)
    retained=radius<=cutoff; edges=torch.linspace(0,cutoff,bins+1); ids=torch.bucketize(radius,edges,right=False)-1; ids[ids==bins]=bins-1
    counts=[int(((ids==index)&retained).sum()) for index in range(bins)]
    if any(count==0 for count in counts): raise ProtocolFailure("empty retained-Nyquist radial frequency bin")
    return {"cutoff":float(cutoff),"edges":edges.tolist(),"retained_counts":counts,"excluded_corner_shell_count":int((~retained).sum()),"rightmost_edge_included":True}


def atomic_checkpoint(path:Path,payload:dict[str,Any])->str:
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as handle: temporary=Path(handle.name)
    try:
        torch.save(payload,temporary); os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()
    return sha256(path)


def atomic_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded=json.dumps(payload,indent=2,sort_keys=True).encode("utf-8")
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_bytes(encoded); os.replace(temporary,path)
    return sha256(path)


def load_checkpoint(path:Path, expected_condition:str)->dict[str,Any]:
    payload=torch.load(path,map_location="cpu",weights_only=False)
    if payload.get("condition_id")!=expected_condition: raise ProtocolFailure("checkpoint condition identity mismatch")
    return payload


def calibration_only_smoke(config: dict[str, Any]) -> dict[str, Any]:
    """Two-step non-scientific development smoke; it never requests test data."""
    factory=DeterministicSplitFactory(config); results=[]
    task_specs={"elliptic_poisson_darcy":(2,1,2,False),"cross_resolution_fields":(1,1,2,False),
                "multiscale_forecasting":(3,3,1,False),"coordinate_permutation":(2,1,2,False),"tabular_control":(1,1,2,True)}
    for task,(inch,outch,dimension,scalar) in task_specs.items():
        data=factory.generate(task,"calibration",limit=2)
        for condition in config["models"]:
            torch.manual_seed(0); model=build_capacity_model(condition,dimension=dimension,in_channels=inch,out_channels=outch,scalar=scalar,config=config)
            optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-4)
            for _ in range(2):
                prediction=model(data.x)
                if dimension == 1 and prediction.shape[-1] != data.y.shape[-1]:
                    prediction=F.interpolate(prediction,size=data.y.shape[-1],mode="linear",align_corners=False)
                loss=F.mse_loss(prediction,data.y)
                if not torch.isfinite(loss): raise ProtocolFailure(f"non-finite calibration smoke loss: {task}:{condition}")
                optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); optimizer.step()
            results.append({"condition_id":f"{task}:{condition}:0","steps":2,"examples":2,"loss":float(loss.detach()),"parameter_count":parameter_count(model)})
    return {"label":"non_scientific_smoke","runner_raw_sha256":sha256(Path(__file__)),"training_seed":0,"split":"calibration","test_data_accessed":False,"spectral_utility_verdict":None,"conditions":results}


def write_r1_preexecution_evidence(root: Path, artifact_dir: Path) -> dict[str, str]:
    """Write manifests permitted before any final evaluation."""
    config=load_frozen_protocol(root)
    sources=[root / relative for relative in RUNNER_SOURCE_RELATIVE_PATHS]
    source=canonical_source_manifest(root,sources)
    source.update({"protocol_id":config["protocol_id"],"p10_sha256":P10_SHA256,"p11_sha256":P11_SHA256,"reference_193_sha256":sha256(root/"fermion/hr/reference_193.py")})
    return {"source_manifest_sha256":atomic_json(artifact_dir/"source_manifest.json",source),"environment_sha256":atomic_json(artifact_dir/"environment.json",environment_manifest())}


@dataclass(frozen=True)
class ConditionIdentity:
    task: str; model: str; training_seed: int
    @property
    def value(self) -> str: return f"{self.task}:{self.model}:{self.training_seed}"


class FullPairedRunner:
    """P1.1 full-run entry point; final data stays impossible without opt-in.

    ``run`` deliberately requires ``allow_final_test=True``.  A launch record
    must be checked by the caller before that value can be supplied.
    """
    tasks=("elliptic_poisson_darcy","cross_resolution_fields","multiscale_forecasting","coordinate_permutation","tabular_control")
    def __init__(self, root: Path, output: Path, *, source_manifest_path: Path | None = None,
                 source_manifest_raw_sha256: str | None = None) -> None:
        torch.use_deterministic_algorithms(True)
        self.root,self.output=root,output; self.config=load_frozen_protocol(root); self.factory=DeterministicSplitFactory(self.config); self.gate=FinalTestAccessGate()
        self.source_manifest_path,self.source_manifest_raw_sha256=source_manifest_path,source_manifest_raw_sha256
        self.runner_raw_sha256=sha256(Path(__file__))
        self.output.mkdir(parents=True,exist_ok=True)
    def identities(self) -> tuple[ConditionIdentity,...]:
        return tuple(ConditionIdentity(task,model,seed) for task in self.tasks for model in self.config["models"] for seed in self.config["training_seeds"])
    def _shape(self, task:str) -> tuple[int,int,int,bool]:
        return {"elliptic_poisson_darcy":(2,1,2,False),"cross_resolution_fields":(1,1,2,False),"coordinate_permutation":(2,1,2,False),"multiscale_forecasting":(3,3,1,False),"tabular_control":(1,1,2,True)}[task]
    def _checkpoint_path(self, identity:ConditionIdentity) -> Path: return self.output/"checkpoints"/f"{identity.value.replace(':','__')}.pt"
    def _progress_path(self, identity:ConditionIdentity) -> Path: return self.output/"checkpoints"/f"{identity.value.replace(':','__')}.progress.pt"
    def _forward(self, model:nn.Module, data:SplitData, dimension:int) -> Tensor:
        prediction=model(data.x)
        if dimension==1 and prediction.shape[-1]!=data.y.shape[-1]: prediction=F.interpolate(prediction,size=data.y.shape[-1],mode="linear",align_corners=False)
        return prediction
    def _learning_rate(self, step: int) -> float:
        train=self.config["training"]; initial=float(train["initial_learning_rate"]); final=float(train["schedule"]["final_learning_rate"]); warmup=int(train["warmup_steps"]); total=int(train["steps_per_model_task_seed"])
        if step <= warmup: return initial * step / warmup
        progress=(step-warmup)/(total-warmup)
        return final + .5*(initial-final)*(1+math.cos(math.pi*progress))
    def _verify_before_test_unseal(self) -> None:
        if self.source_manifest_path is None or self.source_manifest_raw_sha256 is None:
            raise ProtocolFailure("final-test unseal requires a detached source manifest and raw SHA-256")
        verify_source_manifest(self.root,self.source_manifest_path,manifest_raw_sha256=self.source_manifest_raw_sha256)
        if sha256(Path(__file__)) != self.runner_raw_sha256: raise ProtocolFailure("runner changed during execution")
        load_frozen_protocol(self.root)
    def select_on_validation(self, identity:ConditionIdentity) -> dict[str,Any]:
        """Train/select without loading any test data."""
        inch,outch,dimension,scalar=self._shape(identity.task); torch.manual_seed(identity.training_seed)
        model=build_capacity_model(identity.model,dimension=dimension,in_channels=inch,out_channels=outch,scalar=scalar,config=self.config)
        optimizer=torch.optim.AdamW(model.parameters(),lr=self.config["training"]["initial_learning_rate"],weight_decay=self.config["training"]["weight_decay"])
        train=self.factory.generate(identity.task,"train"); validation=self.factory.generate(identity.task,"validation")
        target_mean=train.y.mean(dim=0,keepdim=True); target_std=train.y.std(dim=0,keepdim=True).clamp_min(1e-6)
        generator=torch.Generator().manual_seed(identity.training_seed); best=float("inf"); best_step=None; best_state=None; start=1; last_gradient_norm=0.0
        steps=int(self.config["training"]["steps_per_model_task_seed"]); interval=int(self.config["training"]["validation_interval_steps"]); batch=int(self.config["training"]["batch_size"])
        progress_path=self._progress_path(identity)
        if progress_path.exists():
            progress=load_checkpoint(progress_path,identity.value)
            if progress.get("runner_raw_sha256") != self.runner_raw_sha256: raise ProtocolFailure("resume checkpoint runner hash mismatch")
            model.load_state_dict(progress["state_dict"]); optimizer.load_state_dict(progress["optimizer"]); generator.set_state(progress["generator_state"])
            best=float(progress["best"]); best_step=progress.get("best_step"); best_state=progress.get("best_state"); start=int(progress["step"])+1
        for step in range(start,steps+1):
            rate=self._learning_rate(step)
            for group in optimizer.param_groups: group["lr"]=rate
            index=torch.randint(len(train.x),(batch,),generator=generator); sample=SplitData(train.task,train.split,train.x[index],train.y[index],train.metadata)
            prediction=self._forward(model,sample,dimension); loss=normalized_mse(prediction,sample.y,target_mean,target_std).mean()
            if not torch.isfinite(loss): raise ProtocolFailure(f"non-finite training loss: {identity.value}")
            optimizer.zero_grad(); loss.backward(); last_gradient_norm=float(torch.nn.utils.clip_grad_norm_(model.parameters(),self.config["training"]["gradient_clip_norm"])); optimizer.step()
            if step%interval==0:
                with torch.no_grad(): value=float(normalized_mse(self._forward(model,validation,dimension),validation.y,target_mean,target_std).mean())
                if not np.isfinite(value): raise ProtocolFailure(f"non-finite validation loss: {identity.value}")
                if value<best: # strict comparison implements earliest checkpoint tie-break.
                    best,best_step=value,step
                    best_state={key:value.detach().clone() for key,value in model.state_dict().items()}
                atomic_checkpoint(progress_path,{"condition_id":identity.value,"runner_raw_sha256":self.runner_raw_sha256,"step":step,"state_dict":model.state_dict(),"optimizer":optimizer.state_dict(),"generator_state":generator.get_state(),"best":best,"best_step":best_step,"best_state":best_state,"target_mean":target_mean,"target_std":target_std})
        if best_step is None: raise ProtocolFailure(f"missing validation checkpoint: {identity.value}")
        atomic_checkpoint(self._checkpoint_path(identity),{"condition_id":identity.value,"runner_raw_sha256":self.runner_raw_sha256,"step":best_step,"validation_normalized_mse":best,"state_dict":best_state,"target_mean":target_mean,"target_std":target_std,"gradient_norm":last_gradient_norm})
        self.gate.select(identity.task,identity.model,identity.training_seed)
        return {"condition_id":identity.value,"selected_step":best_step,"validation_normalized_mse":best,"checkpoint":str(self._checkpoint_path(identity)),"training_budget_steps":steps,"gradient_norm":last_gradient_norm,"parameter_count":parameter_count(model)}
    def _frequency_diagnostic(self, prediction: Tensor, target: Tensor, *, resolution: int | None) -> dict[str, Any]:
        error=prediction-target
        if error.ndim != 4:
            return {"available":False,"reason":"not_a_2d_field"}
        bins=radial_frequency_bins(error.shape[-2],error.shape[-1]); spectrum=torch.fft.fftn(error,dim=(-2,-1),norm="ortho").abs().square().mean((0,1)); target_power=torch.fft.fftn(target,dim=(-2,-1),norm="ortho").abs().square().mean((0,1));
        ky=torch.fft.fftfreq(error.shape[-2],d=1/error.shape[-2])*2*torch.pi; kx=torch.fft.fftfreq(error.shape[-1],d=1/error.shape[-1])*2*torch.pi; radius=torch.sqrt(ky[:,None].square()+kx[None,:].square()); edges=torch.tensor(bins["edges"]); assigned=torch.bucketize(radius,edges,right=False)-1; assigned[assigned==16]=15; retained=radius<=float(bins["cutoff"])
        radial=[]
        for index in range(16):
            mask=(assigned==index)&retained; radial.append(float(spectrum[mask].sum()/target_power[mask].sum().clamp_min(1e-30)))
        return {"available":True,"resolution":resolution,"parseval":parseval_audit(error),"radial_error_power_ratio":radial,"excluded_corner_shell_error_power":float(spectrum[~retained].sum()),"excluded_corner_shell_target_power":float(target_power[~retained].sum()),"common_physical_mode_cutoff":float(math.pi*32)}
    def _collapse_diagnostic(self, model: nn.Module, data: SplitData) -> dict[str, Any]:
        with torch.no_grad():
            activation=model.input(data.x) if isinstance(model,CapacityModel) else None
            output=self._forward(model,data,self._shape(data.task)[2])
        if isinstance(model,CapacityModel) and model.gate is not None:
            gate=float(model.gate.detach()); return {"transfer_function":{"kind":"scalar_residual_gate","value":1+math.tanh(gate)},"gate_value":gate,"activation_residual_ratio":float(activation.norm()/data.x.norm().clamp_min(1e-30)),"output_norm":float(output.norm())}
        return {"transfer_function":None,"gate_value":None,"activation_residual_ratio":None,"output_norm":float(output.norm())}
    def evaluate_selected_test_once(self, identity:ConditionIdentity) -> tuple[list[dict[str,Any]],list[dict[str,Any]],dict[str,Any]]:
        """Only callable after validation selection; no selection logic lives here."""
        checkpoint=load_checkpoint(self._checkpoint_path(identity),identity.value); inch,outch,dimension,scalar=self._shape(identity.task)
        model=build_capacity_model(identity.model,dimension=dimension,in_channels=inch,out_channels=outch,scalar=scalar,config=self.config); model.load_state_dict(checkpoint["state_dict"]); model.eval(); rows=[]; frequency=[]; collapse=None
        for split in ("test_id","test_ood"):
            if identity.task=="tabular_control" and split=="test_ood": continue
            resolutions=(32,64,128) if identity.task=="cross_resolution_fields" else (None,)
            for resolution in resolutions:
                self._verify_before_test_unseal()
                data=self.factory.generate(identity.task,split,gate=self.gate,model=identity.model,training_seed=identity.training_seed,resolution=resolution)
                with torch.no_grad(): prediction=self._forward(model,data,dimension); losses=normalized_mse(prediction,data.y,checkpoint["target_mean"],checkpoint["target_std"])
                if not torch.isfinite(losses).all(): raise ProtocolFailure(f"non-finite final loss: {identity.value}:{split}")
                rows.extend({"condition_id":identity.value,"task":identity.task,"model":identity.model,"training_seed":identity.training_seed,"split":split,"resolution":resolution,"realization":index,"normalized_loss":float(value)} for index,value in enumerate(losses))
                frequency.append({"condition_id":identity.value,"split":split,"resolution":resolution,**self._frequency_diagnostic(prediction,data.y,resolution=resolution)})
                collapse=self._collapse_diagnostic(model,data)
        return rows,frequency,{"condition_id":identity.value,"gradient_norm":checkpoint["gradient_norm"],**(collapse or {})}
    def run(self, *, allow_final_test: bool=False) -> dict[str,Any]:
        if not allow_final_test: raise ProtocolFailure("full paired execution is gated; final-test access requires launch authorization")
        self._verify_before_test_unseal()
        selected=[self.select_on_validation(identity) for identity in self.identities()]
        evaluations=[self.evaluate_selected_test_once(identity) for identity in self.identities()]
        rows=[row for values,_,_ in evaluations for row in values]; frequency=[item for _,values,_ in evaluations for item in values]; collapse=[item for _,_,item in evaluations]
        return self.write_final_artifacts(selected,rows,frequency,collapse)
    def _required_endpoint_check(self, rows: list[dict[str, Any]]) -> None:
        for identity in self.identities():
            present={(row["split"],row.get("resolution")) for row in rows if row["condition_id"]==identity.value}
            required={("test_id",None)} if identity.task=="tabular_control" else {("test_id",None),("test_ood",None)}
            if identity.task=="cross_resolution_fields": required={(split,resolution) for split in ("test_id","test_ood") for resolution in (32,64,128)}
            if not required.issubset(present): raise ProtocolFailure(f"required test endpoint missing: {identity.value}")
    def _paired_bootstrap(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        output={}; primary={"elliptic_poisson_darcy":("test_ood",None),"cross_resolution_fields":("test_ood",(64,128)),"multiscale_forecasting":("test_ood",None),"coordinate_permutation":("test_ood",None),"tabular_control":("test_id",None)}
        for task,(split,resolution) in primary.items():
            grouped: dict[tuple[str,int,int], list[float]]={}
            for row in rows:
                if row["task"]!=task or row["split"]!=split or row["model"] not in {"spectral","spectral_ablation"}: continue
                if resolution is None:
                    if row.get("resolution") is not None: continue
                elif row.get("resolution") not in resolution: continue
                grouped.setdefault((row["model"],int(row["training_seed"]),int(row["realization"])),[]).append(float(row["normalized_loss"]))
            values={}
            for model in ("spectral","spectral_ablation"):
                per_seed=[]
                for seed in self.config["training_seeds"]:
                    realized=[(idx,items) for (kind,current,idx),items in grouped.items() if kind==model and current==seed]
                    realized.sort(); expected=self.factory.count("elliptic_poisson_darcy" if task=="coordinate_permutation" else task,split)
                    if len(realized)!=expected or [idx for idx,_ in realized] != list(range(expected)): raise ProtocolFailure(f"missing paired bootstrap realizations: {task}:{model}:{seed}")
                    per_seed.append([float(np.mean(items)) for _,items in realized])
                values[model]=np.asarray(per_seed)
            improvement,lower,upper=deterministic_hierarchical_bootstrap(values["spectral"],values["spectral_ablation"],seed=int(self.config["bootstrap"]["seed"]),resamples=int(self.config["bootstrap"]["resamples"]))
            output[task]={"spectral_loss":float(values["spectral"].mean()),"ablation_loss":float(values["spectral_ablation"].mean()),"relative_improvement":improvement,"percentile_95_ci":[lower,upper],"resamples":int(self.config["bootstrap"]["resamples"]),"success_component":improvement>=.05 and lower>0,"negative_control":task in {"coordinate_permutation","tabular_control"}}
        if len(output)!=5: raise ProtocolFailure("missing required task bootstrap")
        return output
    def write_final_artifacts(self, selected:list[dict[str,Any]], rows:list[dict[str,Any]], frequency:list[dict[str,Any]], collapse:list[dict[str,Any]]) -> dict[str,Any]:
        if not rows: raise ProtocolFailure("cannot finalize empty results")
        self._required_endpoint_check(rows)
        conditions=[{"condition_id":identity.value,"normalized_loss":next(row["normalized_loss"] for row in rows if row["condition_id"]==identity.value)} for identity in self.identities()]
        finalize_condition_records(conditions,self.config)
        bootstrap=self._paired_bootstrap(rows)
        frequency_hash=atomic_json(self.output/"frequency_diagnostics.json",{"protocol_id":self.config["protocol_id"],"diagnostics":frequency})
        collapse_hash=atomic_json(self.output/"collapse_diagnostics.json",{"protocol_id":self.config["protocol_id"],"diagnostics":collapse})
        bootstrap_hash=atomic_json(self.output/"bootstrap.json",{"protocol_id":self.config["protocol_id"],"tasks":bootstrap})
        results={"protocol_id":self.config["protocol_id"],"selected":selected,"per_realization":rows,"scientific_gate":"BOOTSTRAP_COMPLETE_NO_AUTOMATIC_UTILITY_CLAIM"}
        results_hash=atomic_json(self.output/"results.json",results)
        csv_path=self.output/"results.csv"; temporary=csv_path.with_suffix(".csv.tmp")
        with temporary.open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        os.replace(temporary,csv_path)
        manifest={"results_sha256":results_hash,"results_csv_sha256":sha256(csv_path),"frequency_diagnostics_sha256":frequency_hash,"collapse_diagnostics_sha256":collapse_hash,"bootstrap_sha256":bootstrap_hash,"checkpoint_count":len(selected),"condition_count":len(self.identities()),"required_model_training_conditions":90,"all_test_endpoints_verified":True,"bootstrap_resamples":10000}
        manifest_hash=atomic_json(self.output/"final_manifest.json",manifest)
        return {"results_sha256":results_hash,"final_manifest_sha256":manifest_hash}
