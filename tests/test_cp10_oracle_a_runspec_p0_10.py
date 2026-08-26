import json
import math
from pathlib import Path
import pytest
from fermion.cp10 import oracle_a_p0_10 as o

def test_frozen_specs_round_trip_and_compatibility():
    assert len(o.FROZEN_RUN_SPECS)==3
    assert [x.role for x in o.FROZEN_RUN_SPECS]==["coarse","medium","fine"]
    assert o.FROZEN_SPECS==tuple(x.to_json() for x in o.FROZEN_RUN_SPECS)
    assert o.frozen_json_specs()==[x.to_json() for x in o.FROZEN_RUN_SPECS]
    for x in o.FROZEN_RUN_SPECS:
        assert x.validate() and o.RunSpec.from_json(json.loads(json.dumps(x.to_json())))==x
        assert len(x.record_times)==len(x.record_indices)==21 and x.record_indices[-1]==x.step_count

@pytest.mark.parametrize("mutate",[
    lambda x:x.pop("N"),lambda x:x.update(extra=1),lambda x:x.update(N=True),lambda x:x.update(N=32.0),
    lambda x:x.update(dt=0),lambda x:x.update(T=math.nan),lambda x:x.update(run_id=""),lambda x:x.update(role=""),
    lambda x:x.update(record_times=()),lambda x:x.update(record_indices=[]),lambda x:x.update(record_times=[0,0,1]),
    lambda x:x.update(record_indices=[0,0,400]),lambda x:x.update(record_indices=[0,20,399])])
def test_runspec_rejects_malformed(mutate):
    x=o.FROZEN_RUN_SPECS[0].to_json(); mutate(x)
    with pytest.raises((ValueError,TypeError)):o.RunSpec.from_json(x)

def test_core_and_synthetic_denials(monkeypatch):
    with pytest.raises(TypeError):o._integrate_core({},None)
    x=o.FROZEN_RUN_SPECS[0].to_json()
    with pytest.raises(PermissionError):o.integrate_synthetic(x,None)
    x["run_id"]="small";x["N"]=9
    with pytest.raises(ValueError):o.integrate_synthetic(x,None)

BASE=o.FROZEN_RUN_SPECS[0].to_json()
REQUIRED_CASE_IDS={
"missing_run_id","missing_N","missing_dt","missing_T","missing_step_count","missing_role","missing_record_times","missing_record_indices","extra_key","input_none","input_list","input_tuple","input_string",
"N_bool","N_zero","N_negative","N_float","N_string","N_null","step_bool","step_zero","step_negative","step_float","step_string","step_null",
*[f"{k}_{v}" for k in ("dt","T") for v in ("bool","zero","negative","nan","positive_inf","negative_inf","string","null")],
*[f"{k}_{v}" for k in ("run_id","role") for v in ("empty","null","integer","list")],
"times_tuple","times_dict","times_null","indices_tuple","indices_dict","indices_null","empty_times","empty_indices","unequal_lengths_times_short","unequal_lengths_indices_short",
"time_bool","time_string","time_null","time_nan","time_positive_inf","time_negative_inf","time_negative","duplicate_times","decreasing_times","nonzero_first_time","terminal_time_mismatch","nonintegral_time_over_dt",
"index_bool","index_float","index_string","index_null","index_negative","duplicate_indices","decreasing_indices","nonzero_first_index","terminal_index_mismatch","altered_interior_index"}
def badcases():
 out={}
 for k in list(BASE):
  y=BASE.copy();y.pop(k);out['missing_'+k]=y
 out.update(extra_key={**BASE,'extra':1},input_none=None,input_list=[],input_tuple=(),input_string='x')
 for k,vals in {'N':[True,0,-1,32.0,'32',None],'step_count':[True,0,-1,400.0,'400',None]}.items():
  for n,v in zip(['bool','zero','negative','float','string','null'],vals):out[f'{k.replace("step_count","step")}_{n}']={**BASE,k:v}
 for k in ('dt','T'):
  for n,v in zip(['bool','zero','negative','nan','positive_inf','negative_inf','string','null'],[True,0,-1,float('nan'),float('inf'),-float('inf'),'x',None]):out[f'{k}_{n}']={**BASE,k:v}
 for k in ('run_id','role'):
  for n,v in zip(['empty','null','integer','list'],['',None,1,[]]):out[f'{k}_{n}']={**BASE,k:v}
 for n,v in [('times_tuple',()),('times_dict',{}),('times_null',None),('indices_tuple',()),('indices_dict',{}),('indices_null',None),('empty_times',[]),('empty_indices',[])]:
  y=BASE.copy();y['record_times' if n.startswith(('times','empty_times')) else 'record_indices']=v;out[n]=y
 for n,key,val in [('unequal_lengths_times_short','record_times',BASE['record_times'][:-1]),('unequal_lengths_indices_short','record_indices',BASE['record_indices'][:-1]),('time_bool','record_times',[True]+BASE['record_times'][1:]),('time_string','record_times',['x']+BASE['record_times'][1:]),('time_null','record_times',[None]+BASE['record_times'][1:]),('time_nan','record_times',[float('nan')]+BASE['record_times'][1:]),('time_positive_inf','record_times',[float('inf')]+BASE['record_times'][1:]),('time_negative_inf','record_times',[-float('inf')]+BASE['record_times'][1:]),('time_negative','record_times',[-.1]+BASE['record_times'][1:]),('duplicate_times','record_times',[0,0]+BASE['record_times'][2:]),('decreasing_times','record_times',[0,.1,.05]+BASE['record_times'][3:]),('nonzero_first_time','record_times',[.1]+BASE['record_times'][1:]),('terminal_time_mismatch','record_times',BASE['record_times'][:-1]+[.9]),('nonintegral_time_over_dt','record_times',[0,.051]+BASE['record_times'][2:]),('index_bool','record_indices',[True]+BASE['record_indices'][1:]),('index_float','record_indices',[0.0]+BASE['record_indices'][1:]),('index_string','record_indices',['x']+BASE['record_indices'][1:]),('index_null','record_indices',[None]+BASE['record_indices'][1:]),('index_negative','record_indices',[-1]+BASE['record_indices'][1:]),('duplicate_indices','record_indices',[0,0]+BASE['record_indices'][2:]),('decreasing_indices','record_indices',[0,40,20]+BASE['record_indices'][3:]),('nonzero_first_index','record_indices',[1]+BASE['record_indices'][1:]),('terminal_index_mismatch','record_indices',BASE['record_indices'][:-1]+[399]),('altered_interior_index','record_indices',BASE['record_indices'][:4]+[81]+BASE['record_indices'][5:])]:
  y=BASE.copy();y[key]=val;out[n]=y
 return out
CASES=badcases()
@pytest.mark.parametrize('case_id,value',list(CASES.items()),ids=list(CASES))
def test_exhaustive_runspec_rejection(case_id,value):
    with pytest.raises((ValueError,TypeError)):o.RunSpec.from_json(value)
def test_case_id_coverage_and_candidate_authority():
    assert set(CASES)==REQUIRED_CASE_IDS and len(CASES)==len(set(CASES))
    candidate=json.loads(Path('protocols/cp10_p0_10_ORACLE_A_COMPLETION_CANDIDATE.json').read_text())
    runs=candidate['oracle_definitions']['oracle_a']['runs']
    assert [x['run_id'] for x in runs]==[x.run_id for x in o.FROZEN_RUN_SPECS]
