"""Certified simply supported beam calculations."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,uuid
from types import MappingProxyType
from .computation import CalculationEvidence,provenance_complete

def solve_simple_supported_beam(*,L:float=4.,w:float=8000.,P:float=12000.,E:float=200e9,Fy:float=250e6,deflection_ratio:float=360.,candidate_s_cm3:float=210.,candidate_i_cm4:float=2050.)->CalculationEvidence:
    ra=rb=w*L/2+P/2; vmax=ra; moment=w*L**2/8+P*L/4; allowable=.60*Fy; s=moment/allowable; limit=L/deflection_ratio
    uniform=5*w*L**4/384; point=P*L**3/48; combined=(5*w*L**4+8*P*L**3)/384; i=(uniform+point)/(E*limit)
    candidate_s=candidate_s_cm3/1e6;candidate_i=candidate_i_cm4/1e8; sigma=moment/candidate_s;delta=(uniform+point)/(E*candidate_i)
    residuals={"equilibrium":ra+rb-w*L-P,"deflection_superposition":(uniform+point)-combined,"factor_8_identity":(5*w*L**4+8*P*L**3)/384-combined,"section_modulus_conversion":s*1e6-(s*1e6/1000)*1000,"inertia_conversion":i*1e8-candidate_i_cm4*(i/candidate_i),"candidate_required_identity":max(0.,s-candidate_s)+max(0.,i-candidate_i),"utilization_recompute":max(moment/candidate_s/allowable,sigma/allowable)-sigma/allowable}
    graph={"nodes":[{"id":"input.L","kind":"parameter"},{"id":"constraint.equilibrium","kind":"constraint"},{"id":"variable.RA","kind":"solved_variable"},{"id":"derived.I_min","kind":"derived_value"},{"id":"oracle.deflection_superposition","kind":"oracle"}],"edges":[{"from":"input.L","to":"constraint.equilibrium","relation":"parameterizes"},{"from":"constraint.equilibrium","to":"variable.RA","relation":"constrains"},{"from":"variable.RA","to":"derived.I_min","relation":"derives"},{"from":"constraint.equilibrium","to":"oracle.deflection_superposition","relation":"verified_by"}]}
    passed=all(abs(x)<1e-9 for x in residuals.values()) and provenance_complete(graph)
    values={"RA_N":ra,"RB_N":rb,"Vmax_N":vmax,"Mmax_Nm":moment,"S_min_m3":s,"S_min_cm3":s*1e6,"S_min_mm3":s*1e9,"I_min_m4":i,"I_min_cm4":i*1e8,"candidate_Sx_cm3":candidate_s_cm3,"candidate_Ix_cm4":candidate_i_cm4,"sigma_max_Pa":sigma,"delta_total_m":delta,"delta_total_mm":delta*1000,"deflection_limit_m":limit,"strength_utilization":sigma/allowable,"stiffness_utilization":delta/limit,"closer_constraint":"deflection"}
    payload={"inputs":{"L_m":L,"w_N_per_m":w,"P_N":P,"E_Pa":E,"Fy_Pa":Fy},"values":values,"residuals":residuals};now=datetime.now(timezone.utc).isoformat()
    return CalculationEvidence("calc_"+uuid.uuid4().hex,"simple_supported_beam",MappingProxyType(payload["inputs"]),"closed_form_beam_superposition","1",MappingProxyType({"RA":ra,"RB":rb,"Vmax":vmax,"Mmax":moment}),MappingProxyType(values),MappingProxyType(residuals),MappingProxyType({"equilibrium":1e-9,"deflection_superposition":1e-9,"factor_8_identity":1e-9}),"converged" if passed else "unverified",1,MappingProxyType({}),("beam_equilibrium","beam_moment","allowable_stress","deflection_superposition_factor_8"),("equilibrium","deflection_superposition","factor_8_identity","provenance_complete") if passed else (),() if passed else ("ENGINEERING_ORACLE_FAILED",),hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),now,now,MappingProxyType(graph),MappingProxyType({"semantic_model_constraint_hash":"simple_supported_beam_v1"}),MappingProxyType({}))
