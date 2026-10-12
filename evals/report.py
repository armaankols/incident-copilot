"""Publish only versioned measured runs, with attempted spend and errors."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    runs = [json.loads(p.read_text()) for p in sorted((ROOT/"results").glob("*.json")) if p.name not in ("retrieval.json", "recovery.json", "stopping.json", "evidence.json")]
    runs = [r for r in runs if "metadata" in r]
    md = ["Measured offline baselines and live-model runs on synthetic telemetry. Transport is recorded per experiment.", "",
          "| Run | Transport | Cases | Outcome correct (95% CI) | Errors | Finalization | Total observed API cost | p50 / p95 seconds |",
          "|---|---|---:|---|---:|---|---:|---|"]
    for r in runs:
        s = r["summary"]
        transport = r['metadata'].get('baseline_transport') or ('live LLM + in-memory MCP' if r['config']['agent'] == 'llm' else 'deploy history')
        reasons = sorted({record['termination_reason'] for record in r.get('records', []) if record.get('termination_reason')})
        finalization = (', '.join(reasons) or r.get('trace_review', {}).get('finalization_source', 'not recorded')) if r['config']['agent'] == 'llm' else 'not applicable'
        md.append(f"| {r['name']} | {transport} | {s['n']} | {s['both_correct_acc']}% ({s['both_correct_ci95'][0]}–{s['both_correct_ci95'][1]}) | {s['errors']} | {finalization} | ${s['total_cost_usd']:.6f} | {s['latency_p50_s']:.6f} / {s['latency_p95_s']:.6f} |")
    md += ["", "Outcome accuracy counts a budget-forced abstention as correct on redacted cases; it does not demonstrate model-selected stopping. Finalization is persisted for new runs or derived from reviewed saved traces; older runs may show not recorded. Latency quantiles describe runs without exceptions; diagnostic misses remain included. Failure elapsed time and observed spend remain in JSON records. API cost is calculated from provider-reported token usage at list prices, not reconciled against an invoice. Structured action compatibility is not a remediation-quality score. These small live smoke runs do not establish reliability; see docs/live-v6-validation.md for the latest failed checks, docs/live-v5-validation.md and docs/live-v4-validation.md for prior live findings, and docs/change-evidence.md for the implementation changes."]
    retrieval = ROOT/"results"/"retrieval.json"
    if retrieval.exists():
        md += ["", "Retrieval smoke checks (small author-written query set):"]
        for item in json.loads(retrieval.read_text()):
            md.append(f"- {item['embedder']}: {item['n_queries']} queries, recall@1 {item['recall@1']}%, recall@3 {item['recall@3']}%.")
    recovery = ROOT/"results"/"recovery.json"
    if recovery.exists():
        md += ["", "Version-specific recovery policy lookup (offline structured reader, not an LLM ablation):", "",
               "| Retrieval | Exact policies | Correct unknown-version abstentions |", "|---|---:|---:|"]
        for run in json.loads(recovery.read_text())["runs"]:
            s = run["summary"]
            md.append(f"| {run['mode']} | {s['exact_policy_correct']}/{s['supported_cases']} | {s['correct_abstentions']}/{s['unknown_version_cases']} |")
    stopping = ROOT/"results/stopping.json"
    if stopping.exists():
        s = json.loads(stopping.read_text())["summary"]
        md += ["", "Offline replay of the recorded missing-evidence query schedule (not new model behavior):",
               f"- Original live schedule: {s['original_live_model_calls']} model calls, {s['original_live_tool_calls']} tool calls.",
               f"- New policy replay: {s['scripted_responses_consumed']} scripted responses, {s['tool_executions']} MCP executions, {s['cache_hits']} cache hits, {s['skipped_requests']} skipped requests; stopped by {s['termination_reason']}.",
               "- Zero provider calls in this replay; it does not measure live-model accuracy, cost or stopping behavior."]
    evidence = ROOT/"results/evidence.json"
    if evidence.exists():
        s = json.loads(evidence.read_text())["summary"]
        md += ["", "Offline deployment/configuration evidence gate (template-specific deterministic checks, not LLM accuracy):",
               f"- {s['assessments']} service/fault assessments across {s['scenarios']} original and correlated-v2 scenarios: {s['supported_positives']}/{s['positive_cases']} expected supports accepted, {s['rejected_negatives']}/{s['negative_cases']} unsupported pairs rejected, {s['false_supports']} false supports.",
               "- Zero provider calls. These checks cover the simulator's known release/exception and DB-pool configuration patterns; they do not prove causality or generalize to arbitrary production faults."]
    text = "\n".join(md)
    (ROOT/"results"/"RESULTS.md").write_text(text+"\n")
    readme = ROOT/"README.md"
    body = readme.read_text()
    a, b = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    if a in body and b in body:
        readme.write_text(body.split(a)[0]+a+"\n"+text+"\n"+b+body.split(b)[1])
    print(text)


if __name__ == "__main__":
    main()
