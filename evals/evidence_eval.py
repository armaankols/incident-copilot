"""Offline change-assessment matrix; not agent accuracy or causal validation."""
import hashlib
import json
from pathlib import Path

from copilot.checks import change_check
from copilot.diagnosis import PROMPT_VERSION
from copilot.sim import SERVICES
from .cases import scenarios

ROOT = Path(__file__).resolve().parents[1]


def evaluate():
    cases = scenarios(60, 0) + scenarios(24, 0, "correlated-v2")
    records = []
    for sc in cases:
        for service in SERVICES:
            for fault in ("bad_deploy", "config_error"):
                available = sc.availability("logs", service) == "available" and sc.availability("deploys") == "available"
                check = change_check(sc.logs, sc.deploys, sc.now, service, fault, available=available)
                # Labels are used only here to score this deterministic gate.
                expected = service == sc.root_service and fault == sc.fault_type
                records.append(dict(case_id=sc.case_id, service=service, fault_type=fault,
                                    expected_supported=expected, status=check["status"]))
    positives = [r for r in records if r["expected_supported"]]
    negatives = [r for r in records if not r["expected_supported"]]
    digest = hashlib.sha256()
    for p in sorted(list((ROOT/"copilot").glob("*.py"))+list((ROOT/"evals").glob("*.py"))):
        digest.update(str(p.relative_to(ROOT)).encode())
        digest.update(p.read_bytes())
    data = [dict(case_id=sc.case_id, metrics=sc.metrics, logs=sc.logs, deploys=sc.deploys,
                 telemetry_availability=sc.telemetry_availability) for sc in cases]
    return dict(mode="offline-template-specific-change-assessment", prompt_version=PROMPT_VERSION,
                source_sha256=digest.hexdigest(), dataset_sha256=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
                suites=["original", "correlated-v2"],
                summary=dict(scenarios=len(cases), assessments=len(records), positive_cases=len(positives),
                             supported_positives=sum(r["status"] == "supported" for r in positives),
                             negative_cases=len(negatives), rejected_negatives=sum(r["status"] != "supported" for r in negatives),
                             false_supports=sum(r["status"] == "supported" for r in negatives), provider_calls=0), records=records)


def main():
    result = evaluate()
    (ROOT/"results/evidence.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
