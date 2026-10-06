"""Assert fixture reproducibility, not claims about live model ability."""
import json
from pathlib import Path

runs = [json.loads(p.read_text()) for p in Path("results").glob("*.json") if p.name not in ("retrieval.json", "recovery.json")]
for suite, n, expected in (("original", 60, 100), ("correlated-v1", 24, 33.3)):
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
