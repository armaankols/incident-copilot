"""Assert fixture reproducibility, not claims about live model ability."""
import json
from pathlib import Path

runs = [json.loads(p.read_text()) for p in Path("results").glob("*.json") if p.name not in ("retrieval.json", "recovery.json", "stopping.json", "evidence.json", "references.json")]
for suite, n, expected in (("original", 60, 100), ("correlated-v1", 24, 33.3), ("correlated-v2", 24, 33.3)):
    matched = [r for r in runs if r["config"].get("agent") == "rules" and r["config"].get("suite") == suite and r["summary"]["n"] == n]
    if not matched:
        raise SystemExit(f"Missing {suite} run")
    latest = max(matched, key=lambda r: r["metadata"]["started_at"])
    if latest["summary"]["errors"] or latest["summary"]["both_correct_acc"] != expected:
        raise SystemExit(f"Unexpected fixture result for {suite}")
print("Offline baseline fixtures match expected measured outcomes")

recovery_path = Path("results/recovery.json")
if not recovery_path.exists():
    raise SystemExit("Missing recovery lookup evaluation")
recovery = json.loads(recovery_path.read_text())
for run in recovery["runs"]:
    s = run["summary"]
    expected = 12 if run["mode"] == "tfidf" else 0
    if s["exact_policy_correct"] != expected or s["correct_abstentions"] != 3:
        raise SystemExit("Unexpected recovery policy lookup fixture result")
print("Recovery lookup fixture outcomes verified")

stopping = json.loads(Path("results/stopping.json").read_text())["summary"]
if (stopping["provider_calls"] != 0 or stopping["outcome"] != "insufficient_evidence"
        or stopping["scripted_responses_consumed"] >= stopping["original_live_model_calls"]
        or stopping["tool_executions"] >= stopping["original_live_tool_calls"]):
    raise SystemExit("Unexpected recorded-query stopping replay result")
print("Recorded-query stopping replay verified; no claim about new model behavior")

evidence = json.loads(Path("results/evidence.json").read_text())["summary"]
if (evidence["assessments"] != 3528 or evidence["positive_cases"] != 78
        or evidence["supported_positives"] != 78 or evidence["negative_cases"] != 3450
        or evidence["rejected_negatives"] != 3450 or evidence["false_supports"] != 0
        or evidence["compact_submissions_accepted"] != 78
        or evidence["compact_submission_max_utf8_bytes"] > 300
        or evidence["constructed_compact_traffic_submission_utf8_bytes"] >= evidence["recorded_v6_traffic_submission_utf8_bytes"]
        or evidence["provider_calls"] != 0):
    raise SystemExit("Unexpected template-specific change assessment result")
print("Six-fault assessment and compact payload fixtures verified; no claim about live-model accuracy")

refs = json.loads(Path("results/references.json").read_text())["summary"]
if (refs["provider_calls"] != 0 or not refs["correct_diagnosis"]
        or refs["root_service"] != "search" or refs["fault_type"] != "traffic_spike"
        or refs["action"] is not None or refs["recovery_status"] != "blocked"
        or refs["scripted_responses_consumed"] != 8 or refs["tool_executions"] != 16
        or refs["validation_rejections"] != 2 or refs["exact_server_excerpts"] != 3):
    raise SystemExit("Unexpected migrated-reference replay outcome")
print("Migrated observation-ID replay verified; no claim about new model behavior")
