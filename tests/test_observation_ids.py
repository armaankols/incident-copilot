"""ID-only model evidence resolves to exact server excerpts; no provider calls."""
import asyncio
import copy
import json

import pytest

from copilot.agent import SUBMIT_TOOL
from copilot.diagnosis import SCHEMA, insufficient, validate_diagnosis
from copilot.llm import ScriptedLLM
from copilot.runner import run_scenario
from copilot.sim import generate
from evals.reference_eval import evaluate, migrate
from tests.evidence import fault_observation


def candidate(ids=None):
    return dict(status='diagnosed',root_cause_service='search',fault_type='traffic_spike',
                evidence=['obs-1'] if ids is None else ids,action=None,target=None)


def test_schema_asks_for_unique_ids_only_and_server_resolves_without_mutation():
    evidence=SUBMIT_TOOL['input_schema']['properties']['evidence']
    assert evidence['items']['type']=='string' and evidence['uniqueItems']
    d=candidate()
    original=copy.deepcopy(d)
    source=fault_observation()
    accepted=validate_diagnosis(d,{'obs-1':source},{'obs-1':'check_fault'})
    assert d==original
    assert accepted['evidence']==[dict(observation_id='obs-1',quote='"status": "supported"')]
    assert accepted['evidence'][0]['quote'] in source
    assert set(SCHEMA['required'])==set(d)


@pytest.mark.parametrize('ids',[
    ['obs-1','obs-1'], ['obs-1']*4, [''], ['x'*65], [None], [17], [True],
    ['obs-1',dict(observation_id='obs-1',quote='supported')],
])
def test_bad_id_inputs_are_rejected(ids):
    with pytest.raises(ValueError):
        validate_diagnosis(candidate(ids),{'obs-1':fault_observation()},{'obs-1':'check_fault'})


def test_unknown_id_feedback_lists_only_available_observations():
    with pytest.raises(ValueError,match='Successful observation IDs: obs-1'):
        validate_diagnosis(candidate(['obs-99']),{'obs-1':fault_observation()},{'obs-1':'check_fault'})


@pytest.mark.parametrize('source',['','   ','ERROR: provider/tool failed',None])
def test_unusable_observations_do_not_become_generated_citations(source):
    with pytest.raises(ValueError,match='usable evidence'):
        validate_diagnosis(candidate(),{'obs-1':source},{'obs-1':'check_fault'})


@pytest.mark.parametrize('change,tool',[
    ({},'search_runbooks'), ({'service':'inventory'},'check_fault'),
    ({'fault_type':'slow_dependency'},'check_fault'), ({'status':'unknown'},'check_fault'),
    ({'kind':'capacity'},'check_fault'),
])
def test_id_selection_cannot_bypass_trusted_service_fault_checks(change,tool):
    check=dict(kind='fault',service='search',fault_type='traffic_spike',status='supported')
    source=json.dumps({**check,**change})
    with pytest.raises(ValueError,match='check_fault'):
        validate_diagnosis(candidate(),{'obs-1':source},{'obs-1':tool})


def test_matching_assessment_must_be_selected_and_conflicts_cannot_be_hidden():
    good=fault_observation()
    unknown=fault_observation(status='unknown')
    with pytest.raises(ValueError,match='check_fault'):
        validate_diagnosis(candidate(['obs-2']),{'obs-1':good,'obs-2':'search metrics'}, {'obs-1':'check_fault','obs-2':'query_metrics'})
    with pytest.raises(ValueError,match='unknown'):
        validate_diagnosis(candidate(),{'obs-1':good,'obs-2':unknown},{'obs-1':'check_fault','obs-2':'check_fault'})


@pytest.mark.parametrize('source',['{"kind":"fault","service":"search","fault_type":"traffic_spike","status":"supported"}',
                                    '{\n "status" :\n "supported", "kind":"fault", "service":"search", "fault_type":"traffic_spike"\n}'])
def test_assessment_excerpt_preserves_actual_json_spacing(source):
    d=validate_diagnosis(candidate(),{'obs-1':source},{'obs-1':'check_fault'})
    quote=d['evidence'][0]['quote']
    assert quote in source and json.loads('{'+quote+'}')['status']=='supported'


def test_metric_and_service_excerpts_are_actual_source_substrings():
    observations={'obs-1':fault_observation(),
                  'obs-2':'search.rps latest=991\nsamples: 13:00=190, 13:55=908',
                  'obs-3':'Time now: 13:59:00\ngateway | 473\nsearch | 1005'}
    tools={'obs-1':'check_fault','obs-2':'query_metrics','obs-3':'list_services'}
    d=validate_diagnosis(candidate(['obs-1','obs-2','obs-3']),observations,tools)
    assert d['evidence'][1]['quote']=='search.rps latest=991'
    assert d['evidence'][2]['quote']=='search | 1005'
    assert all(ref['quote'] in observations[ref['observation_id']] for ref in d['evidence'])


def test_generated_excerpt_is_bounded_without_rewriting_source():
    d=validate_diagnosis(candidate(['obs-1','obs-2']),{'obs-1':fault_observation(),'obs-2':'x'*1000},
                         {'obs-1':'check_fault','obs-2':'query_metrics'})
    assert d['evidence'][1]['quote']=='x'*240


def test_failed_mcp_output_id_is_not_selectable_then_correction_can_succeed():
    sc=generate(5,'traffic_spike')
    use=lambda name,args,id:dict(type='tool_use',name=name,input=args,id=id)
    script=[[use('missing_tool',{},'failed'),use('check_fault',dict(service='search',fault_type='traffic_spike'),'fault')],
            [use('submit_diagnosis',candidate(['obs-1','obs-2']),'bad')],
            [use('submit_diagnosis',candidate(['obs-2']),'fixed')]]
    r=asyncio.run(run_scenario(sc,ScriptedLLM(script),max_steps=3))
    assert r['error'] is None and r['grade']['both_ok']
    assert r['validation_rejections']==1 and r['model_calls']==3 and r['tool_calls']==2
    assert r['diagnosis']['evidence'][0]['observation_id']=='obs-2'


def test_cached_assessment_id_stays_selectable_without_another_execution():
    use=lambda name,args,id:dict(type='tool_use',name=name,input=args,id=id)
    args=dict(service='search',fault_type='traffic_spike')
    script=[[use('check_fault',args,'first')],[use('check_fault',args,'repeat')],
            [use('submit_diagnosis',candidate(),'done')]]
    r=asyncio.run(run_scenario(generate(5,'traffic_spike'),ScriptedLLM(script)))
    assert r['grade']['both_ok'] and r['tool_calls']==1 and r['cache_hits']==1
    assert r['diagnosis']['evidence'][0]['observation_id']=='obs-1'


def test_migration_changes_only_quote_representation_and_recorded_replay_passes():
    from evals.reference_eval import FIXTURE
    fixture=json.loads(FIXTURE.read_text())
    before=copy.deepcopy(fixture['script'])
    after=migrate(before)
    assert before==fixture['script']
    for old_response,new_response in zip(before,after):
        for old,new in zip(old_response,new_response):
            if old['name']=='submit_diagnosis':
                assert new['input']['evidence']==[ref['observation_id'] for ref in old['input']['evidence']]
                assert {k:v for k,v in old['input'].items() if k!='evidence'}=={k:v for k,v in new['input'].items() if k!='evidence'}
            else:
                assert new==old
    result=asyncio.run(evaluate())
    s=result['summary']
    assert s['provider_calls']==0 and s['correct_diagnosis']
    assert s['scripted_responses_consumed']==8 and s['tool_executions']==16 and s['validation_rejections']==2
    assert s['action'] is None and s['recovery_status']=='blocked'
    assert s['exact_server_excerpts']==s['evidence_references']==3
    assert all('check_change' in err and 'unknown' in err for err in result['validation_errors'])


def test_malformed_service_cannot_crash_service_row_resolution_in_graph():
    use=lambda name,args,id:dict(type='tool_use',name=name,input=args,id=id)
    malformed={**candidate(),'root_cause_service':['search']}
    final={k:insufficient()[k] for k in SCHEMA['required']}
    script=[[use('list_services',{},'health')],
            [use('submit_diagnosis',malformed,'bad')],
            [use('submit_diagnosis',final,'stop')]]
    r=asyncio.run(run_scenario(generate(5,'traffic_spike'),ScriptedLLM(script)))
    assert r['error'] is None and r['validation_rejections']==1
    assert r['model_calls']==3 and r['termination_reason']=='model_submission'
    assert r['diagnosis']['status']=='insufficient_evidence'
