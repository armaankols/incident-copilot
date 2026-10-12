"""All diagnoses need local affirmative evidence, including with null recovery."""
import asyncio
import copy
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from copilot.checks import fault_check
from copilot.diagnosis import SCHEMA, validate_diagnosis
from copilot.llm import ScriptedLLM
from copilot.mcp_server import build_server
from copilot.runner import run_scenario
from copilot.sim import SERVICES, generate
from evals.cases import scenarios

FAULTS = ('memory_leak', 'slow_dependency', 'traffic_spike')


def assessment(sc, service=None, fault=None):
    service, fault = service or sc.root_service, fault or sc.fault_type
    available = sc.availability('logs', service) == 'available' and sc.availability('metrics', service) == 'available'
    return fault_check(sc.logs, sc.metrics, sc.now, service, fault, available=available)


@pytest.mark.parametrize('fault,offset', [('memory_leak',1),('slow_dependency',2),('traffic_spike',5)])
def test_supported_original_and_paraphrased_patterns_use_only_observable_data(fault, offset):
    for suite in ('original','correlated-v2'):
        sc=scenarios(1,0,suite,offset=offset)[0]
        check=assessment(sc)
        assert check['status']=='supported' and check['evidence'] and check['metric_summary']
        for other in SERVICES:
            if other != sc.root_service:
                assert assessment(sc, other)['status']=='unknown'
        service=sc.root_service
        sc.root_service,sc.fault_type='gateway','config_error'
        assert assessment(sc,service,fault)==check


@pytest.mark.parametrize('fault',FAULTS)
@pytest.mark.parametrize('mutation',['no_logs','flat_metrics','stale','unavailable','wrong_service','malformed_metrics'])
def test_faults_fail_closed_when_local_corroboration_is_absent(fault, mutation):
    sc=generate(1,fault)
    service=sc.root_service
    available=True
    if mutation=='no_logs':
        sc.logs=[]
    elif mutation=='flat_metrics':
        sc.metrics={s:{k:[v[0]]*len(v) for k,v in m.items()} for s,m in sc.metrics.items()}
    elif mutation=='stale':
        sc.logs=[(m-30,s,level,msg) for m,s,level,msg in sc.logs]
    elif mutation=='unavailable':
        available=False
    elif mutation=='wrong_service':
        service=next(s for s in SERVICES if s!=service)
    else:
        sc.metrics[service]={k:[float('nan')]*len(v) for k,v in sc.metrics[service].items()}
    assert fault_check(sc.logs,sc.metrics,sc.now,service,fault,available=available)['status']=='unknown'


def test_oom_restart_alone_does_not_establish_memory_leak():
    sc=generate(1,'memory_leak')
    sc.metrics[sc.root_service]['memory_mb']=[520.0]*120
    assert assessment(sc)['status']=='unknown'


def test_recent_plateau_after_memory_regrowth_remains_supported():
    for seed in (25,49):
        sc=generate(seed,'memory_leak')
        assert sc.metrics[sc.root_service]['memory_mb'][-5:]==[1019.0]*5
        assert assessment(sc)['status']=='supported'


def test_slow_dependency_requires_named_current_caller_timeout():
    sc=generate(2,'slow_dependency')
    sc.logs=[r for r in sc.logs if 'timeout after' not in r[3]]
    sc.logs.append((sc.now,'gateway','ERROR','upstream requests failing'))
    assert assessment(sc)['status']=='unknown'
    sc.logs.append((sc.now+1,'orders','ERROR',f'timeout after 1000ms calling {sc.root_service}'))
    assert assessment(sc)['status']=='unknown'


def test_traffic_needs_both_increased_load_and_local_overload_evidence():
    sc=generate(5,'traffic_spike')
    assert assessment(sc)['status']=='supported'
    sc.logs=[r for r in sc.logs if 'rate limiter shedding load' not in r[3]]
    assert assessment(sc)['status']=='unknown'  # max replicas alone is not traffic proof


@pytest.mark.parametrize('fault',FAULTS)
def test_gate_requires_correct_trusted_cited_service_fault_and_status(fault):
    check=dict(kind='fault',service='auth',fault_type=fault,status='supported')
    d=dict(status='diagnosed',root_cause_service='auth',fault_type=fault,evidence=[dict(observation_id='obs-1',quote='"kind": "fault"')],action=None,target=None)
    for update,tool,cite in [({},'search_runbooks',True),({'service':'orders'},'check_fault',True),
                             ({'fault_type':'config_error'},'check_fault',True),({'status':'unknown'},'check_fault',True),
                             ({},'check_fault',False)]:
        text=json.dumps({**check,**update})
        proposed=d if cite else {**d,'evidence':[dict(observation_id='obs-2',quote='gateway symptom')]}
        with pytest.raises(ValueError,match='check_fault'):
            validate_diagnosis(proposed,{'obs-1':text,'obs-2':'gateway symptom'},{'obs-1':tool})
    with pytest.raises(ValueError,match='unknown'):
        validate_diagnosis(d,{'obs-1':json.dumps(check),'obs-2':json.dumps({**check,'status':'unknown'})},
                           {'obs-1':'check_fault','obs-2':'check_fault'})


def test_saved_auth_guess_cannot_pass_with_short_genuine_quotes_and_no_action():
    root=Path(__file__).resolve().parents[1]
    record=json.loads((root/'results/live-v6-missing_evidence-2026-10-12-ec2fe2431647.json').read_text())['records'][0]
    d={k:record['diagnosis'][k] for k in SCHEMA['required']}
    observations={r['observation_id']:r['quote'] for r in d['evidence']}
    d['evidence']=[{**r,'quote':r['quote'][:240]} for r in d['evidence'][:3]]
    sc=scenarios(1,0,'correlated-v2',offset=18)[0]
    check=assessment(sc,'auth','slow_dependency')
    assert check['status']=='unknown' and check['coverage']=='unavailable'
    observations['obs-check']=json.dumps(check)
    with pytest.raises(ValueError,match='check_fault.*unknown'):
        validate_diagnosis(d,observations,{'obs-check':'check_fault'})


def test_real_mcp_does_not_leak_hidden_records_when_coverage_is_unavailable():
    async def collect(sc):
        async with create_connected_server_and_client_session(build_server(sc,use_rag=False)) as session:
            output=[]
            for fault in FAULTS:
                r=await session.call_tool('check_fault',dict(service='auth',fault_type=fault))
                assert not r.isError
                output.append(json.loads(r.content[0].text))
            return output
    sc=generate(1,'memory_leak')
    sc.telemetry_availability={'logs':{'auth':'unavailable'},'metrics':{'auth':'unavailable'}}
    for r in asyncio.run(collect(sc)):
        assert r['status']=='unknown' and r['coverage']=='unavailable' and r['evidence']==[]
        assert 'metric_summary' not in r
