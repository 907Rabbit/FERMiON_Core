import pytest
import json
from pathlib import Path
from dataclasses import FrozenInstanceError
from fermion.cp10 import oracle_a_p0_10 as o

def expected():
    return o._LaunchAuthorityInputs('A'*64,'B'*64,'C'*64,'482D3EA675350BA359E66B61D381D0CA929CA7A2E02B56F5D07848C763506540','artifacts/cp10_p0_10_oracle_a/',o.FROZEN_RUN_SPECS)
def payload():
    e=expected();return {'protocol_id':'CP10-P0.10','status':'AUTHORIZED','authorization_scope':'ORACLE_A_THREE_RUN_VERIFICATION_ONLY','freeze_receipt_sha256':e.freeze_receipt_sha256,'solver_sha256':e.solver_sha256,'launcher_sha256':e.launcher_sha256,'source_manifest_sha256':e.source_manifest_sha256,'output_root':e.output_root,'run_ids':list(e.run_ids),'run_tuples':[x.to_json() for x in e.run_specs],'execution_id':'test-1','utc_authorization_timestamp':'2026-08-25T00:00:00Z','oracle_b':False,'scientific_conditions':False,'held_out_access':False,'bootstrap':False}
def test_valid_and_immutable():
    x=o._validate_launch_payload(payload(),expected());assert x.solver_sha256=='A'*64 and x.run_specs==o.FROZEN_RUN_SPECS and x.oracle_b is False
    with pytest.raises(FrozenInstanceError):x.run_specs[0].N=1
    with pytest.raises(FrozenInstanceError):expected().run_specs=[]
def test_hash_normalization_and_candidate_authority():
    assert o._normalize_sha256('a'*64)=='A'*64
    for x in [None,b'a'*64,1,True,'a'*63,'g'*64]:
        with pytest.raises(ValueError):o._normalize_sha256(x)
    specs,audit=o.candidate_run_authority()
    assert specs==o.FROZEN_RUN_SPECS
    assert len(audit)==3 and all(x['runspec_equal'] and 'comparison_targets' in x for x in audit)
@pytest.mark.parametrize('key',['protocol_id','status','authorization_scope','freeze_receipt_sha256','solver_sha256','launcher_sha256','source_manifest_sha256','output_root','run_ids','run_tuples','execution_id','utc_authorization_timestamp','oracle_b','scientific_conditions','held_out_access','bootstrap'])
def test_missing(key):
    x=payload();x.pop(key)
    with pytest.raises(ValueError):o._validate_launch_payload(x,expected())
@pytest.mark.parametrize('key,value',[('oracle_b',0),('oracle_b',True),('execution_id',''),('execution_id','x\n'),('utc_authorization_timestamp','2026-08-25T00:00:00+01:00'),('run_ids',[]),('run_tuples',[])])
def test_rejections(key,value):
    x=payload();x[key]=value
    with pytest.raises(ValueError):o._validate_launch_payload(x,expected())
