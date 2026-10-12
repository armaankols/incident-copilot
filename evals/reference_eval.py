"""Replay recorded selections through the ID interface; no new model behavior."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

from copilot.diagnosis import PROMPT_VERSION
from copilot.llm import ScriptedLLM
from copilot.runner import run_scenario
from .cases import scenarios

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'evals/fixtures/v7-traffic-reference-schedule.json'


def migrate(script):
    """Keep every hypothesis/selected source; only remove provider quote prose."""
    migrated = copy.deepcopy(script)
    for response in migrated:
        for block in response:
            if block['name'] == 'submit_diagnosis':
                block['input']['evidence'] = [ref['observation_id'] for ref in block['input']['evidence']]
    return migrated


async def evaluate():
    fixture = json.loads(FIXTURE.read_text())
    sc = scenarios(1, fixture['seed'], fixture['suite'], offset=fixture['case_offset'])[0]
    result = await run_scenario(sc, ScriptedLLM(migrate(fixture['script'])))
    if result['error']:
        raise RuntimeError(result['error'])
    observations = {e['observation_id']: e['output'] for e in result['trace'] if e['type']=='tool_result' and e.get('observation_id')}
    refs = result['diagnosis']['evidence']
    source = hashlib.sha256()
    for p in sorted(list((ROOT/'copilot').glob('*.py'))+list((ROOT/'evals').glob('*.py'))+list((ROOT/'runbooks').glob('*.md'))):
        source.update(str(p.relative_to(ROOT)).encode()); source.update(p.read_bytes())
    return dict(mode='offline-migrated-reference-replay', source_run=fixture['source_run'],
                prompt_version=PROMPT_VERSION, source_sha256=source.hexdigest(),
                fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), case_id=sc.case_id,
                summary=dict(original_live_model_calls=fixture['original_model_calls'],
                             original_live_tool_calls=fixture['original_tool_calls'],
                             original_live_validation_rejections=fixture['original_validation_rejections'],
                             scripted_responses_consumed=result['model_calls'], tool_executions=result['tool_calls'],
                             tool_requests=result['tool_requests'], validation_rejections=result['validation_rejections'],
                             output_truncations=result['output_truncations'], termination_reason=result['termination_reason'],
                             outcome=result['diagnosis']['status'], root_service=result['diagnosis']['root_cause_service'],
                             fault_type=result['diagnosis']['fault_type'], action=result['diagnosis']['action'],
                             recovery_status=result['diagnosis']['recovery_status'], correct_diagnosis=result['grade']['both_ok'],
                             evidence_references=len(refs), exact_server_excerpts=sum(ref['quote'] in observations[ref['observation_id']] for ref in refs),
                             provider_calls=0), diagnosis=result['diagnosis'],
                validation_errors=[e['output'] for e in result['trace'] if e['type']=='validation_error'])


def main():
    result = asyncio.run(evaluate())
    (ROOT/'results/references.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))


if __name__ == '__main__':
    main()
