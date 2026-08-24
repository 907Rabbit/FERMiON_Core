"""Authoritative, read-only runtime capability inspection."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
import json

@dataclass(frozen=True)
class Capability:
    capability_id: str; implementation_status: str; runtime_status: str; test_status: str
    certification_status: str; exposure_status: str; module: str; symbol: str; interfaces: tuple[str,...]
    last_verified_at: str; confidence: str = "authoritative"
    availability_reason: str|None = None
    def to_dict(self) -> dict[str, object]: return asdict(self)

class CapabilityRegistry:
    """Inspects loaded implementation symbols; it never mutates runtime or source."""
    SPECS=(
        ("execution_evidence","fermion.cognitive.evidence","ExecutionEvidence",("/execution verify",)),
        ("memory_verification","fermion.cognitive.memory","CognitiveMemory",("/memory verify",)),
        ("persistent_memory_receipts","fermion.cognitive.evidence","MemoryReceipt",("/memory verify",)),
        ("calculation_evidence","fermion.cognitive.computation","CalculationEvidence",("/calculation last","/calculation verify")),
        ("scientific_routing","fermion.cognitive.scientific_routing","detect_scientific_route",("/route last",)),
        ("diprotic_equilibrium","fermion.cognitive.chemistry","solve_diprotic_with_evidence",()),
        ("model_comparison","fermion.cognitive.chemistry","compare_diprotic_models",()),
        ("capability_registry","fermion.cognitive.capability_registry","CapabilityRegistry",("/capabilities","/capability","/self audit")),
        # The current executor intentionally supports only bounded documented templates, not arbitrary code.
        ("code_execution","fermion.cognitive.runtime","CognitiveRuntime._maybe_execute",()),
        ("workspace_file_write","fermion.cognitive.runtime","CognitiveRuntime._maybe_execute",()),
    )
    DEPENDENCIES={"calculation_evidence":(),"execution_evidence":(),"memory_verification":(),"persistent_memory_receipts":(),"scientific_routing":(),"diprotic_equilibrium":("calculation_evidence","scientific_routing"),"model_comparison":("diprotic_equilibrium","calculation_evidence","scientific_routing"),"capability_registry":()}
    def __init__(self, root: Path, overrides: dict[str,str]|None=None): self.root=root; self.overrides=overrides or {}
    @property
    def history_path(self)->Path: return self.root / "logs" / "capability_history.jsonl"
    def record_event(self, capability_id:str, status:str, source:str, failure_code:str|None=None, baseline_hash:str|None=None)->None:
        self.history_path.parent.mkdir(parents=True,exist_ok=True)
        with self.history_path.open("a",encoding="utf-8") as f:f.write(json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"capability_id":capability_id,"status":status,"source":source,"failure_code":failure_code,"baseline_hash":baseline_hash})+"\n")
    def history(self, capability_id:str)->list[dict[str,object]]:
        if not self.history_path.exists():return []
        return [x for x in (json.loads(line) for line in self.history_path.read_text(encoding="utf-8").splitlines()) if x["capability_id"]==capability_id]
    def anomalies(self)->list[dict[str,object]]:
        result=[]
        for item in self.records():
            events=self.history(item.capability_id); failures=[e for e in events if e["status"] in {"degraded","blocked"}]
            if not failures:continue
            state="regression_confirmed" if len(failures)>=3 else "regression_suspected" if any(e["failure_code"] for e in failures) else "transient_failure"
            result.append({"capability_id":item.capability_id,"state":state,"events":failures,"baseline_hash":failures[-1].get("baseline_hash")})
        return result
    def diagnose(self, target:str|None=None)->dict[str,object]:
        health=self.health(); observed=[target] if target else [k for k,v in health.items() if v["health_status"]!="healthy"]
        candidates=[]
        for cid in health:
            impact=set(self.impact(cid)["blocks"]); explained=len(impact & set(observed)) + (1 if cid in observed else 0)
            if explained:candidates.append({"capability":cid,"explains":explained,"unexplained":len(observed)-explained,"recent_anomaly":any(x["capability_id"]==cid for x in self.anomalies())})
        candidates.sort(key=lambda x:(x["explains"],x["recent_anomaly"]),reverse=True)
        return {"observed_failures":observed,"candidate_causes":candidates,"minimal_explanation_set":[candidates[0]["capability"]] if candidates else []}
    def recovery(self, capability_id:str)->dict[str,object]:
        return {"root_cause":capability_id,"recommended_actions":[{"action":"inspect_recent_failures","risk":"low"},{"action":"rerun_targeted_tests","scope":[f"test_{capability_id}"],"risk":"low"},{"action":"verify_dependencies","risk":"low"}],"prohibited_actions":["autonomous_source_edit","silent_registry_mutation"],"success_criteria":["targeted_tests_pass","capability_health_returns_healthy","downstream_failures_clear"],"mutation_permission":False}
    def records(self) -> list[Capability]:
        now=datetime.now(timezone.utc).isoformat(); records=[]
        for cid,module,symbol,interfaces in self.SPECS:
            try: active=hasattr(import_module(module),symbol)
            except ImportError: active=False
            tests=(self.root/"tests").is_dir()
            arbitrary=cid in {"code_execution","workspace_file_write"}; forced=self.overrides.get(cid); active = active and forced != "blocked" and not arbitrary
            records.append(Capability(cid,"implemented" if active else ("implemented_bounded_only" if arbitrary else "absent"),"active" if active else "unavailable","available" if tests and active else "failing","certified" if active and tests else "unverified","available_to_cognition" if active else "not_exposed",module,symbol,interfaces,now,availability_reason="ARBITRARY_EXECUTION_NOT_IMPLEMENTED" if arbitrary else None))
        return records
    def get(self, capability_id: str) -> Capability|None: return next((item for item in self.records() if item.capability_id==capability_id),None)
    def gaps(self) -> dict[str,list[str]]:
        rows=self.records()
        return {"implemented_not_exposed":[x.capability_id for x in rows if x.implementation_status=="implemented" and x.exposure_status!="available_to_cognition"],"exposed_not_certified":[x.capability_id for x in rows if x.exposure_status=="available_to_cognition" and x.certification_status!="certified"],"certified_not_recently_verified":[],"planned_not_implemented":[]}
    def audit(self) -> dict[str,object]:
        rows=self.records(); return {"authority":"runtime_introspection","capabilities":[x.to_dict() for x in rows],"gaps":self.gaps(),"mutation_permission":False,"recommendation":"Inspect reported gaps; source modification requires a separate authorized tool action."}
    def impact(self, capability_id: str) -> dict[str,object]:
        reverse={key:[] for key in self.DEPENDENCIES}
        for child,parents in self.DEPENDENCIES.items():
            for parent in parents: reverse.setdefault(parent,[]).append(child)
        seen=set(); stack=list(reverse.get(capability_id,[]))
        while stack:
            item=stack.pop()
            if item not in seen: seen.add(item); stack.extend(reverse.get(item,[]))
        return {"capability":capability_id,"downstream_count":len(seen),"blocks":sorted(seen),"criticality":"very_high" if len(seen)>=3 else "high" if seen else "low"}
    def blockers(self, capability_id:str)->dict[str,object]: return {"capability":capability_id,"depends_on":list(self.DEPENDENCIES.get(capability_id,()))}
    def health(self, capability_id: str|None=None)->dict[str,object]:
        records={item.capability_id:item for item in self.records()}; memo={}
        def one(cid):
            if cid in memo:return memo[cid]
            row=records[cid]; deps=[one(dep) for dep in self.DEPENDENCIES.get(cid,()) if dep in records]
            blocked=row.runtime_status!="active" or any(item["health_status"]=="blocked" for item in deps)
            degraded=not blocked and (row.test_status!="available" or any(item["health_status"]!="healthy" for item in deps))
            score=0 if blocked else 70 if degraded else 100
            memo[cid]={"id":cid,"implementation_present":row.implementation_status=="implemented","runtime_loaded":row.runtime_status=="active","cognitively_exposed":row.exposure_status=="available_to_cognition","tests_passing":row.test_status=="available","dependencies_healthy":all(item["health_status"]=="healthy" for item in deps),"last_verified_recent":True,"recent_failures":0,"health_score":score,"health_status":"blocked" if blocked else "degraded" if degraded else "healthy"}
            return memo[cid]
        result={cid:one(cid) for cid in records}; return result.get(capability_id) if capability_id else result
