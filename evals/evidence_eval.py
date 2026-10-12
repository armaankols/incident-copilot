"""Offline six-fault assessment matrix; not agent accuracy or causal proof."""
import hashlib
import json
from pathlib import Path

from copilot.checks import certificate_check, change_check, fault_check
from copilot.diagnosis import PROMPT_VERSION, validate_diagnosis
from copilot.sim import FAULT_TYPES, SERVICES, callers_of
from .cases import scenarios

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT/'evals/fixtures/v6-traffic-final-submission.json'


def assessment(sc, service, fault):
    if fault in ('bad_deploy', 'config_error'):
        available = sc.availability('logs', service) == 'available' and sc.availability('deploys') == 'available'
        return change_check(sc.logs, sc.deploys, sc.now, service, fault, available=available), 'check_change', 'supported'
    if fault == 'cert_expiry':
        available = all(sc.availability('logs', s) == 'available' for s in [service]+callers_of(service))
        return certificate_check(sc.logs if available else [], sc.now, service), 'check_certificate', 'expiry_supported'
    log_sources = [service]+(callers_of(service) if fault == 'slow_dependency' else [])
    available = sc.availability('metrics', service) == 'available' and all(sc.availability('logs', s) == 'available' for s in log_sources)
    return fault_check(sc.logs, sc.metrics, sc.now, service, fault, available=available), 'check_fault', 'supported'


def submission(service, fault):
    return dict(status='diagnosed', root_cause_service=service, fault_type=fault,
                evidence=['obs-1'], action=None, target=None)


def size(d):
    return len(json.dumps(d, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))


def evaluate():
    cases = scenarios(60, 0)+scenarios(24, 0, 'correlated-v2')
    records, payload_sizes = [], []
    accepted_compact = 0
    for sc in cases:
        for service in SERVICES:
            for fault in FAULT_TYPES:
                check, tool, supported = assessment(sc, service, fault)
                # Injected labels score the gate here only; helpers do not read them.
                expected = service == sc.root_service and fault == sc.fault_type
                records.append(dict(case_id=sc.case_id, service=service, fault_type=fault,
                                    expected_supported=expected, status=check['status'], supported=check['status']==supported))
                if expected:
                    d = submission(service, fault)
                    accepted = validate_diagnosis(d, {'obs-1':json.dumps(check)}, {'obs-1':tool})
                    accepted_compact += accepted['status'] == 'diagnosed'
                    payload_sizes.append(size(d))
    positives = [r for r in records if r['expected_supported']]
    negatives = [r for r in records if not r['expected_supported']]
    digest = hashlib.sha256()
    for p in sorted(list((ROOT/'copilot').glob('*.py'))+list((ROOT/'evals').glob('*.py'))):
        digest.update(str(p.relative_to(ROOT)).encode())
        digest.update(p.read_bytes())
    data = [dict(case_id=sc.case_id, metrics=sc.metrics, logs=sc.logs, deploys=sc.deploys,
                 telemetry_availability=sc.telemetry_availability) for sc in cases]
    fixture = json.loads(FIXTURE.read_text())
    return dict(mode='offline-template-specific-six-fault-assessment', prompt_version=PROMPT_VERSION,
                source_sha256=digest.hexdigest(), dataset_sha256=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), suites=['original','correlated-v2'],
                summary=dict(scenarios=len(cases), assessments=len(records), positive_cases=len(positives),
                             supported_positives=sum(r['supported'] for r in positives), negative_cases=len(negatives),
                             rejected_negatives=sum(not r['supported'] for r in negatives), false_supports=sum(r['supported'] for r in negatives),
                             compact_submissions_accepted=accepted_compact, compact_submission_max_utf8_bytes=max(payload_sizes),
                             recorded_v6_traffic_submission_utf8_bytes=size(fixture['submission']),
                             constructed_compact_traffic_submission_utf8_bytes=size(submission('search','traffic_spike')),
                             provider_calls=0), records=records)


def main():
    result = evaluate()
    (ROOT/'results/evidence.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
