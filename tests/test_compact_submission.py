"""Compact payloads and safe output-limit handling; never calls a provider."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from copilot.agent import SUBMIT_TOOL
from copilot.diagnosis import SCHEMA, insufficient, validate_diagnosis
from copilot.llm import LLMResponse
from copilot.runner import run_scenario
from copilot.sim import generate
from evals.run_evals import summarize
from tests.evidence import fault_observation


def use(name, args, id='t'):
    return dict(type='tool_use',id=id,name=name,input=args)


def compact():
    return dict(status='diagnosed',root_cause_service='search',fault_type='traffic_spike',
                evidence=[dict(observation_id='obs-1',quote='"status": "supported"')],action=None,target=None)


class Responses:
    model='scripted'
    def __init__(self, responses):
        self.responses=responses
        self.calls=0
    async def complete(self, system, messages, tools, tool_choice=None):
        self.messages=copy.deepcopy(messages)
        self.calls+=1
        return self.responses[min(self.calls-1,len(self.responses)-1)]


def response(blocks, truncated=False):
    return LLMResponse(blocks,'max_tokens' if truncated else 'tool_use',input_tokens=1000,output_tokens=1000 if truncated else 100)


def test_model_schema_has_six_fields_and_server_generates_advice():
    assert set(SCHEMA['required'])==set(compact())
    assert 'remediation' not in SUBMIT_TOOL['input_schema']['properties']
    accepted=validate_diagnosis(compact(),{'obs-1':fault_observation()},{'obs-1':'check_fault'})
    assert accepted['status']=='diagnosed' and 'No recovery action' in accepted['remediation']
    legacy={**compact(),'remediation':'Invented rollback v999'}
    assert validate_diagnosis(legacy,{'obs-1':fault_observation()},{'obs-1':'check_fault'})==accepted


@pytest.mark.parametrize('update',[
    dict(evidence=[dict(observation_id='obs-1',quote='x')]*4),
    dict(evidence=[dict(observation_id='obs-1',quote='x'*241)]),
    dict(action=None), # overridden below to test a missing field
])
def test_compact_contract_enforces_size_and_required_fields(update):
    d={**compact(),**update}
    if update==dict(action=None):
        del d['target']
    with pytest.raises(ValueError):
        validate_diagnosis(d,{'obs-1':'x'*300},{'obs-1':'check_fault'})


def test_recorded_invalid_quote_stays_invalid_after_size_reduction():
    fixture=json.loads((Path(__file__).resolve().parents[1]/'evals/fixtures/v6-traffic-final-submission.json').read_text())
    ref=next(r for r in fixture['submission']['evidence'] if r['observation_id']=='obs-7')
    d={**compact(),'evidence':[ref]}
    assert len(ref['quote'])<=240
    with pytest.raises(ValueError,match='not an exact substring'):
        validate_diagnosis(d,fixture['observations'])


def test_truncated_complete_diagnosis_and_trailing_tools_are_never_executed():
    final={k:insufficient()[k] for k in SCHEMA['required']}
    llm=Responses([response([use('submit_diagnosis',final,'partial'),use('list_services',{},'health')],True),
                   response([use('submit_diagnosis',final,'complete')])])
    r=asyncio.run(run_scenario(generate(5,'traffic_spike'),llm))
    assert r['error'] is None and r['model_calls']==2 and r['tool_calls']==r['tool_requests']==0
    assert r['output_truncations']==1 and r['validation_rejections']==0
    assert r['usage']['output_tokens']==1100 and r['termination_reason']=='model_submission'
    blocks=llm.messages[-1]['content']
    closed={b['tool_use_id'] for b in blocks if b['type']=='tool_result'}
    assert closed=={'partial','health'}
    assert any(e['type']=='output_truncated' for e in r['trace'])


def test_repeated_truncation_stops_separately_from_invalid_submissions():
    llm=Responses([response([use('submit_diagnosis',{'status':'diagnosed'})],True)])
    r=asyncio.run(run_scenario(generate(5,'traffic_spike'),llm))
    assert r['error'] is None and r['termination_reason']=='output_limit'
    assert r['output_truncations']==r['model_calls']==3 and r['validation_rejections']==0
    assert r['diagnosis']['status']=='insufficient_evidence' and r['tool_calls']==0
    assert r['usage']['output_tokens']==3000
    summary=summarize([r])
    assert summary['forced_abstentions']==1 and summary['total_output_truncations']==3


def test_global_model_budget_still_bounds_truncated_responses():
    llm=Responses([response([use('list_services',{})],True)])
    r=asyncio.run(run_scenario(generate(5,'traffic_spike'),llm,max_steps=2))
    assert r['termination_reason']=='step_budget' and r['model_calls']==2 and r['tool_calls']==0


def test_two_recorded_truncation_shapes_allow_a_later_compact_supported_submission():
    fixture=json.loads((Path(__file__).resolve().parents[1]/'evals/fixtures/v6-traffic-final-submission.json').read_text())
    first={k:fixture['submission'][k] for k in ('status','root_cause_service','fault_type')}
    second={k:v for k,v in fixture['submission'].items() if k!='remediation'}
    llm=Responses([response([use('check_fault',dict(service='search',fault_type='traffic_spike'),'fault')]),
                   response([use('submit_diagnosis',first,'cut1')],True),
                   response([use('submit_diagnosis',second,'cut2')],True),
                   response([use('submit_diagnosis',compact(),'done')])])
    r=asyncio.run(run_scenario(generate(5,'traffic_spike'),llm))
    assert r['error'] is None and r['grade']['both_ok']
    assert r['output_truncations']==2 and r['validation_rejections']==0
    assert r['model_calls']==4 and r['tool_calls']==1 and r['termination_reason']=='model_submission'
    assert r['diagnosis']['action'] is None
