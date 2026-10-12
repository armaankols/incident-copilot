"""Replay a recorded query schedule offline; not a new model evaluation."""
import asyncio
import hashlib
import json
from pathlib import Path

from copilot.diagnosis import PROMPT_VERSION
from copilot.llm import ScriptedLLM
from copilot.runner import run_scenario
from .cases import scenarios

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals/fixtures/missing-evidence-query-schedule.json"


async def evaluate():
    fixture = json.loads(FIXTURE.read_text())
    sc = scenarios(1, fixture["seed"], fixture["suite"], offset=fixture["case_offset"])[0]
    result = await run_scenario(sc, ScriptedLLM(fixture["script"]))
    if result["error"]:
        raise RuntimeError(result["error"])
    source_hash = hashlib.sha256()
    for p in sorted(list((ROOT/"copilot").glob("*.py"))+list((ROOT/"evals").glob("*.py"))+list((ROOT/"runbooks").glob("*.md"))):
        source_hash.update(str(p.relative_to(ROOT)).encode())
        source_hash.update(p.read_bytes())
    return {
        "mode": "offline-recorded-query-replay",
        "source_run": fixture["source_run"],
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "source_sha256": source_hash.hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "case_id": sc.case_id,
        "limits": result["investigation_limits"],
        "summary": {
            "original_live_model_calls": fixture["original_model_calls"],
            "original_live_tool_calls": fixture["original_tool_calls"],
            "scripted_responses_consumed": result["model_calls"],
            "tool_requests": result["tool_requests"],
            "tool_executions": result["tool_calls"],
            "cache_hits": result["cache_hits"],
            "skipped_requests": sum(e["type"] == "tool_skipped" for e in result["trace"]),
            "termination_reason": result["termination_reason"],
            "outcome": result["diagnosis"]["status"],
            "provider_calls": 0,
        },
    }


def main():
    result = asyncio.run(evaluate())
    (ROOT / "results/stopping.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
