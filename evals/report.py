"""Publish only versioned measured runs, with attempted spend and errors."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    runs = [json.loads(p.read_text()) for p in sorted((ROOT/"results").glob("*.json")) if p.name not in ("retrieval.json", "recovery.json")]
    runs = [r for r in runs if "metadata" in r]
    md = ["Measured offline baselines on synthetic telemetry. Transport is recorded per experiment.", "",
          "| Run | Transport | Cases | Outcome correct (95% CI) | Errors | Total observed API cost | p50 / p95 seconds |",
          "|---|---|---:|---|---:|---:|---|"]
    for r in runs:
        s = r["summary"]
        md.append(f"| {r['name']} | {r['metadata'].get('baseline_transport') or 'deploy history'} | {s['n']} | {s['both_correct_acc']}% ({s['both_correct_ci95'][0]}–{s['both_correct_ci95'][1]}) | {s['errors']} | ${s['total_cost_usd']:.6f} | {s['latency_p50_s']:.6f} / {s['latency_p95_s']:.6f} |")
    md += ["", "Outcome accuracy counts a correct abstention on redacted cases. Latency quantiles describe successful runs; failure elapsed time and observed spend remain in JSON records. Structured action compatibility is not a remediation-quality score. No live-model results have been measured."]
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
