"""Assert fixture reproducibility, not claims about live model ability."""
import json
from pathlib import Path

runs = [json.loads(p.read_text()) for p in Path("results").glob("*.json") if p.name != "retrieval.json"]
for suite, n, expected in (("original", 60, 100), ("correlated-v1", 24, 33.3)):
    matched = [r for r in runs if r["config"].get("agent") == "rules" and r["config"].get("suite") == suite and r["summary"]["n"] == n]
    if not matched:
        raise SystemExit(f"Missing {suite} run")
    latest = max(matched, key=lambda r: r["metadata"]["started_at"])
    if latest["summary"]["errors"] or latest["summary"]["both_correct_acc"] != expected:
        raise SystemExit(f"Unexpected fixture result for {suite}")
print("Offline baseline fixtures match expected measured outcomes")
