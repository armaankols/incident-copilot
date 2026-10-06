"""Eval harness: run N simulated incidents through an agent and score against known ground truth.

  python -m evals.run_evals --agent baseline --n 60
  python -m evals.run_evals --agent llm --model claude-haiku-4-5-20251001 --n 30
  python -m evals.run_evals --agent llm --no-rag --n 30        # ablation: runbook search removed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
import uuid
import hashlib
import platform
from datetime import datetime, timezone
from pathlib import Path

from copilot.baselines import baseline_rules, baseline_rules_mcp
from copilot.pricing import DEFAULT_MODEL
from copilot.grading import baseline_latest_deploy, grade
from .cases import VERSION, scenarios
from copilot.sim import FAULT_TYPES, generate

RESULTS = Path(__file__).resolve().parent.parent / "results"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def pct(xs):
    return round(100 * sum(xs) / len(xs), 1) if xs else 0.0


def summarize(records: list[dict]) -> dict:
    n = len(records)
    ok = [r for r in records if not r.get("error")]
    both = sum(r["grade"]["both_ok"] for r in records)
    lo, hi = wilson(both, n)
    lat = sorted(r["latency_s"] for r in ok) or [0.0]
    by_type = {ft: pct([r["grade"]["both_ok"] for r in records if r["fault_type"] == ft]) for ft in FAULT_TYPES}
    return {
        "n": n, "errors": n - len(ok),
        "root_cause_service_acc": pct([r["grade"]["service_ok"] for r in records]),
        "fault_type_acc": pct([r["grade"]["type_ok"] for r in records]),
        "both_correct_acc": pct([r["grade"]["both_ok"] for r in records]),
        "both_correct_ci95": [round(100 * lo, 1), round(100 * hi, 1)],
        "action_compatibility_rate": pct([r["grade"]["remediation_ok"] for r in records]),
        "avg_tool_calls": round(statistics.mean(r["tool_calls"] for r in ok), 2) if ok else 0,
        "avg_steps": round(statistics.mean(r["steps"] for r in ok), 2) if ok else 0,
        "avg_input_tokens": round(statistics.mean(r["usage"]["input_tokens"] + r["usage"]["cache_read_tokens"] + r["usage"]["cache_write_tokens"] for r in ok)) if ok else 0,
        "avg_output_tokens": round(statistics.mean(r["usage"]["output_tokens"] for r in ok)) if ok else 0,
        "avg_cost_usd": round(statistics.mean(r["cost_usd"] for r in records), 6) if records else 0,
        "total_cost_usd": round(sum(r["cost_usd"] for r in records), 6),
        "error_rate": pct([bool(r.get("error")) for r in records]),
        "cost_per_correct_diagnosis_usd": round(sum(r["cost_usd"] for r in records)/both, 6) if both else None,
        "billing_uncertain_runs": sum(bool(r.get("billing_uncertain")) for r in records),
        "latency_scope": "successful runs only",
        "total_attempted_latency_s": round(sum(r["latency_s"] for r in records), 6),
        "latency_p50_s": round(statistics.median(lat), 6),
        "latency_p95_s": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 6),
        "accuracy_by_fault_type": by_type,
        "total_observed_usage": {key: sum(r.get("usage", {}).get(key, 0) for r in records) for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")},
        "outcome_accuracy_by_variant": {variant: pct([r["grade"]["both_ok"] for r in records if r.get("variant") == variant]) for variant in sorted({r.get("variant", "original") for r in records})},
        "insufficient_evidence_cases": sum(r["fault_type"] == "insufficient_evidence" for r in records),
        "abstention_accuracy": pct([r["grade"]["both_ok"] for r in records if r["fault_type"] == "insufficient_evidence"]),
    }


async def evaluate(args) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    cases = scenarios(args.n, args.seed, args.suite)
    if args.n < 1 or args.concurrency < 1 or args.max_steps < 1:
        raise ValueError("n, concurrency and max_steps must be positive")
    records = []
    sem = asyncio.Semaphore(args.concurrency)
    run_id = uuid.uuid4().hex[:12]
    name = (args.name or f"{args.agent}-{args.suite}-seed{args.seed}-{args.embedder}-steps{args.max_steps}-n{args.n}") + f"-{run_id}"
    if Path(name).name != name:
        raise ValueError("name must be a filename")
    RESULTS.mkdir(exist_ok=True)
    checkpoint = RESULTS / f"{name}.jsonl"

    async def one(sc):
        if args.agent in ("baseline", "rules", "rules-mcp"):
            t0 = time.perf_counter()
            d, trace, calls = baseline_rules(sc) if args.agent == "rules" else (baseline_latest_deploy(sc), [], 0)
            if args.agent == "rules-mcp":
                d, trace, calls = await baseline_rules_mcp(sc)
            return {"seed": sc.seed, "fault_type": sc.fault_type, "root_service": sc.root_service, "diagnosis": d,
                    "grade": grade(sc, d), "steps": 0, "tool_calls": calls, "cost_usd": 0.0, "latency_s": time.perf_counter()-t0, "trace": trace,
                    "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}}
        async with sem:
            from copilot.llm import AnthropicLLM
            from copilot.runner import run_scenario
            r = await run_scenario(sc, AnthropicLLM(args.model), use_rag=not args.no_rag,
                                   max_steps=args.max_steps, embedder=args.embedder)
            print(f"  seed={sc.seed} {sc.fault_type:15s} -> {'OK ' if r['grade']['both_ok'] else 'MISS'} "
                  f"tools={r['tool_calls']} ${r['cost_usd']:.3f}" + (f" ERROR {r['error'][:80]}" if r.get('error') else ""), flush=True)
            return r

    async def checkpointed(sc):
        r = await one(sc)
        r.update(case_id=sc.case_id, variant=sc.variant)
        records.append(r)
        with checkpoint.open("a") as f:
            f.write(json.dumps(r) + "\n")
            f.flush()
        return r

    await asyncio.gather(*(checkpointed(sc) for sc in cases))
    records.sort(key=lambda r: r["seed"])
    dataset_hash = hashlib.sha256(json.dumps([{"case_id": sc.case_id, "metrics": sc.metrics, "logs": sc.logs, "deploys": sc.deploys, "truth": [sc.root_service, sc.fault_type]} for sc in cases], sort_keys=True).encode()).hexdigest()
    source_hash = hashlib.sha256()
    root = RESULTS.parent
    for p in sorted(list((root/"copilot").glob("*.py"))+list((root/"evals").glob("*.py"))+list((root/"runbooks").glob("*.md"))):
        source_hash.update(str(p.relative_to(root)).encode())
        source_hash.update(p.read_bytes())
    out = {"name": name, "config": {k: v for k, v in vars(args).items()}, "metadata": {"run_id": run_id, "started_at": started_at,
                 "source_sha256": source_hash.hexdigest(), "dataset_sha256": dataset_hash, "dataset_version": args.suite,
                 "prompt_version": "evidence-v2", "python": platform.python_version(),
                 "baseline_transport": "direct simulator log search" if args.agent == "rules" else "in-memory MCP" if args.agent == "rules-mcp" else None},
           "summary": summarize(records),
           "records": [{k: v for k, v in r.items() if k != "trace"} for r in records]}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(out, indent=2))
    if args.save_traces:
        (RESULTS / "traces").mkdir(exist_ok=True)
        (RESULTS / "traces" / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["llm", "baseline", "rules", "rules-mcp"], default="llm")
    ap.add_argument("--suite", choices=["original", VERSION], default="original")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0, help="base seed; scenario i uses seed*1000+i")
    ap.add_argument("--no-rag", action="store_true")
    ap.add_argument("--embedder", default="tfidf", choices=["tfidf", "fastembed"])
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--save-traces", action="store_true")
    ap.add_argument("--name", default=None)
    args = ap.parse_args()
    out = asyncio.run(evaluate(args))
    print(json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
