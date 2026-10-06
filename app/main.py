"""Bounded synthetic incident demo; single-machine durable admission and replay."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from copilot.budget import AdmissionDenied, Ledger
from copilot.llm import AnthropicLLM
from copilot.pricing import DEFAULT_MODEL, cost_usd
from copilot.runner import run_scenario
from copilot.sim import FAULT_TYPES, generate

STATIC = Path(__file__).parent / "static"
ALLOWED_MODELS = [DEFAULT_MODEL, "claude-sonnet-4-6"]
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "2.0"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "8"))
MAX_STEPS = 12
MAX_INPUT_TOKENS = 24000
MAX_OUTPUT_TOKENS = 1000
app = FastAPI(title="Incident Copilot")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_jobs = {}
_tasks = set()


def ledger():
    return Ledger(os.getenv("BUDGET_DB", "data/demo.sqlite3"))


def make_llm(model):
    return AnthropicLLM(model, max_tokens=MAX_OUTPUT_TOKENS, max_input_tokens=MAX_INPUT_TOKENS)


class InvestigateRequest(BaseModel):
    fault_type: str | None = None
    model: str = DEFAULT_MODEL


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def health():
    ledger().spent()
    return {"status": "ok", "live_model_configured": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.get("/api/config")
def config():
    return {"models": ALLOWED_MODELS, "fault_types": FAULT_TYPES, "daily_budget_usd": DAILY_BUDGET_USD,
            "spent_today_usd": round(ledger().spent(), 3), "live_enabled": bool(os.getenv("ANTHROPIC_API_KEY"))}


def admit(req, request):
    if req.model not in ALLOWED_MODELS:
        raise HTTPException(400, f"model must be one of {ALLOWED_MODELS}")
    if req.fault_type and req.fault_type not in FAULT_TYPES:
        raise HTTPException(400, f"fault_type must be one of {FAULT_TYPES}")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Live investigations require server API credentials; saved replays are available.")
    # Trust proxy headers only on explicitly configured deployments.
    ip = request.client.host if request.client else "unknown"
    if os.getenv("TRUST_FLY_PROXY") == "1":
        ip = request.headers.get("fly-client-ip", ip)
    visitor = hashlib.sha256(ip.encode()).hexdigest()
    # Worst-case 5-minute cache writes on every input token, plus capped output.
    maximum = cost_usd(req.model, {"cache_write_tokens": MAX_INPUT_TOKENS * MAX_STEPS,
                                  "output_tokens": MAX_OUTPUT_TOKENS * MAX_STEPS})
    try:
        return ledger().reserve(maximum, DAILY_BUDGET_USD, visitor, RATE_LIMIT_PER_HOUR)
    except AdmissionDenied as e:
        raise HTTPException(429, str(e)) from e


async def execute(rid, req):
    progress = _jobs.setdefault(rid, {})
    result = None
    try:
        sc = generate(random.randint(10_000, 99_999), req.fault_type)
        progress["alert"] = sc.alert
        result = await run_scenario(sc, make_llm(req.model), max_steps=MAX_STEPS, progress=progress)
        result.update(alert=sc.alert, model=req.model, run_id=rid,
                      ground_truth={"root_service": sc.root_service, "fault_type": sc.fault_type})
        ledger().save_replay(rid, json.dumps(result))
        return result
    finally:
        ledger().settle(rid, cost_usd(req.model, progress.get("usage", {})),
                        uncertain=result is None or progress.get("billing_uncertain", False))
        _jobs.pop(rid, None)


@app.post("/api/investigate")
async def investigate(req: InvestigateRequest, request: Request):
    return await execute(admit(req, request), req)


async def background(rid, req):
    try:
        await execute(rid, req)
    except Exception:
        ledger().save_replay(rid, json.dumps({"run_id": rid, "error": "Investigation failed", "trace": [], "diagnosis": None}))


@app.post("/api/runs", status_code=202)
async def start_run(req: InvestigateRequest, request: Request):
    rid = admit(req, request)
    _jobs[rid] = {"trace": [], "model_calls": 0}
    task = asyncio.create_task(background(rid, req))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": rid}


@app.get("/api/runs/{rid}")
def run_status(rid: str):
    saved = ledger().replay(rid)
    if saved:
        return {"status": "completed", "result": json.loads(saved)}
    if rid in _jobs:
        return {"status": "running", "progress": _jobs[rid]}
    raise HTTPException(404, "Run unavailable; it may have been interrupted by a restart")


@app.get("/api/replay")
def example_replay():
    path = STATIC / "offline-replay.json"
    if not path.exists():
        raise HTTPException(404, "No offline replay has been generated")
    return FileResponse(path)
