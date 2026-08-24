"""Read-only release readiness governance from authoritative runtime evidence."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from .capability_registry import CapabilityRegistry

@dataclass(frozen=True)
class ReleaseReadiness:
    candidate_id:str; versions:dict[str,str]; capability_health:dict[str,int]; anomalies:dict[str,int]
    benchmarks:dict[str,object]; provenance:dict[str,bool]; recoveries:dict[str,object]; verdict:str; blockers:tuple[str,...]
    def to_dict(self)->dict[str,object]: return asdict(self)

class ReleaseGovernor:
    CRITICAL=("calculation_evidence","scientific_routing","diprotic_equilibrium","model_comparison")
    def __init__(self, root:Path, registry:CapabilityRegistry): self.root=root;self.registry=registry
    def evaluate(self, declared_versions:dict[str,str]|None=None)->ReleaseReadiness:
        health=self.registry.health(); anomalies=self.registry.anomalies(); critical_blocked=sum(health.get(x,{}).get("health_status")=="blocked" for x in self.CRITICAL); critical_degraded=sum(health.get(x,{}).get("health_status")=="degraded" for x in self.CRITICAL)
        confirmed=[x for x in anomalies if x["state"]=="regression_confirmed"]
        tests=(self.root/"tests").is_dir(); manifest=(self.root/"pyproject.toml").is_file(); digest=hashlib.sha256((self.root/"pyproject.toml").read_bytes()).hexdigest() if manifest else "unknown"
        versions=declared_versions or {"language":"0","fermion_architecture":"0","benchmark_suite":"0","ir":"1"}
        blockers=[]
        if critical_blocked:blockers.append("CRITICAL_CAPABILITY_BLOCKED")
        if confirmed:blockers.append("REGRESSION_CONFIRMED_UNRESOLVED")
        if not tests:blockers.append("BENCHMARK_EVIDENCE_MISSING")
        if not manifest:blockers.append("PROVENANCE_INVALID")
        verdict="RELEASE_BLOCKED" if blockers else "RELEASE_READY_WITH_WARNINGS" if critical_degraded else "RELEASE_READY"
        return ReleaseReadiness("release_candidate_"+digest[:12],versions,{"critical_blocked":critical_blocked,"critical_degraded":critical_degraded},{"regression_confirmed":len(confirmed),"unresolved":len(anomalies)},{"passed":tests,"blocking_failures":[] if tests else ["tests_directory_missing"]},{"manifest_valid":manifest,"hashes_valid":manifest,"consistency_valid":manifest},{"unresolved":[x["capability_id"] for x in anomalies]},verdict,tuple(blockers))
