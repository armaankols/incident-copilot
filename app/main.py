"""Bounded synthetic incident demo; single-machine durable admission and replay."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr

from app.access import COOKIE, SESSION_SECONDS, check_origin, has_access, make_session, require_access, valid_link_token, valid_sonnet_passcode
from app.security import RequestGuard, visitor_id

from copilot.budget import AdmissionDenied, Ledger
from copilot.llm import AnthropicLLM
from copilot.errors import public_error, public_result
from copilot.pricing import DEFAULT_MODEL, cost_usd
from copilot.runner import run_scenario
from copilot.sim import FAULT_TYPES, generate, generate_undiagnosable

STATIC = Path(__file__).parent / "static"
SONNET_MODEL = "claude-sonnet-4-6"
ALLOWED_MODELS = [DEFAULT_MODEL, SONNET_MODEL]
WEB_FAULT_TYPES = [*FAULT_TYPES, "insufficient_evidence"]
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "2.0"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "8"))
MAX_STEPS = 12
MAX_INPUT_TOKENS = 24000
MAX_OUTPUT_TOKENS = 1000
app = FastAPI(title="Incident Copilot", redirect_slashes=False)


class RevalidatedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", RevalidatedStaticFiles(directory=STATIC), name="static")
_jobs = {}
_tasks = set()


@app.middleware("http")
async def private_api_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def ledger():
    return Ledger(os.getenv("BUDGET_DB", "data/demo.sqlite3"))


app.add_middleware(RequestGuard, ledger_factory=ledger)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    # Default validation errors echo input, including submitted access tokens.
    return JSONResponse({"detail": [{key: item[key] for key in ("loc", "msg", "type")}
                                    for item in error.errors()]}, status_code=422,
                        headers={"Cache-Control": "no-store"})


def make_llm(model):
    return AnthropicLLM(model, max_tokens=MAX_OUTPUT_TOKENS, max_input_tokens=MAX_INPUT_TOKENS)


class InvestigateRequest(BaseModel):
    fault_type: str | None = Field(None, max_length=64)
    model: str = Field(DEFAULT_MODEL, max_length=64)
    sonnet_passcode: SecretStr | None = Field(None, max_length=256, repr=False)


class AccessRequest(BaseModel):
    token: str = Field(max_length=256)


@app.post("/api/access")
def unlock(req: AccessRequest, request: Request):
    check_origin(request)
    if not valid_link_token(req.token):
        raise HTTPException(401, "Agent access link is invalid")
    response = JSONResponse({"agent_access": True})
    response.set_cookie(COOKIE, make_session(), max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.hostname not in ("localhost", "127.0.0.1", "::1"),
                        samesite="strict", path="/api")
    return response


@app.get("/")
def index():
    version = hashlib.sha256((STATIC / "demo.js").read_bytes()).hexdigest()[:16]
    html = (STATIC / "index.html").read_text().replace(
        'src="/static/demo.js"', f'src="/static/demo.js?v={version}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def health():
    ledger().spent()
    return {"status": "ok", "live_model_configured": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.get("/api/config")
def config(request: Request):
    return {"models": ALLOWED_MODELS, "fault_types": WEB_FAULT_TYPES, "daily_budget_usd": DAILY_BUDGET_USD,
            **ledger().budget_status(), "live_enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
            "agent_access": has_access(request), "budget_policy": "start_threshold"}


def admit(req, request):
    require_access(request)
    if req.model not in ALLOWED_MODELS:
        raise HTTPException(400, f"model must be one of {ALLOWED_MODELS}")
    if req.fault_type and req.fault_type not in WEB_FAULT_TYPES:
        raise HTTPException(400, f"fault_type must be one of {WEB_FAULT_TYPES}")
    visitor = visitor_id(request)
    passcode = req.sonnet_passcode.get_secret_value() if req.sonnet_passcode else ""
    req.sonnet_passcode = None  # Never carry a password into execution or replays.
    if req.model == SONNET_MODEL:
        retry_after = ledger().allow_request([("sonnet-password:" + visitor, 20)])
        if retry_after:
            raise HTTPException(429, "Too many Sonnet password attempts. Try again shortly.",
                                headers={"Retry-After": str(retry_after)})
        if not valid_sonnet_passcode(passcode):
            raise HTTPException(403, "A valid owner password is required for Sonnet")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Live investigations require server API credentials; saved replays are available.")
    # Worst-case 5-minute cache writes on every input token, plus capped output.
    maximum = cost_usd(req.model, {"cache_write_tokens": MAX_INPUT_TOKENS * MAX_STEPS,
                                  "output_tokens": MAX_OUTPUT_TOKENS * MAX_STEPS})
    try:
        return ledger().reserve(maximum, DAILY_BUDGET_USD, visitor, RATE_LIMIT_PER_HOUR, start_threshold=True)
    except AdmissionDenied as e:
        raise HTTPException(429, str(e)) from e


async def execute(rid, req):
    progress = _jobs.setdefault(rid, {})
    result = None
    try:
        seed = random.randint(10_000, 99_999)
        sc = generate_undiagnosable(seed) if req.fault_type == "insufficient_evidence" else generate(seed, req.fault_type)
        progress["alert"] = sc.alert
        result = await run_scenario(sc, make_llm(req.model), max_steps=MAX_STEPS, progress=progress)
        result.update(alert=sc.alert, model=req.model, run_id=rid,
                      ground_truth={"root_service": sc.root_service, "fault_type": sc.fault_type})
        ledger().save_replay(rid, json.dumps(result))
        return public_result(result)
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
    except Exception as error:
        ledger().save_replay(rid, json.dumps({"run_id": rid, "error": public_error(error), "trace": [], "diagnosis": None}))


@app.post("/api/runs", status_code=202)
async def start_run(req: InvestigateRequest, request: Request):
    rid = admit(req, request)
    _jobs[rid] = {"trace": [], "model_calls": 0}
    task = asyncio.create_task(background(rid, req))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": rid}


@app.get("/api/runs")
def saved_runs(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0)):
    rows = ledger().saved_runs(limit + 1, offset)
    summaries = []
    for rid, started, payload in rows[:limit]:
        result = json.loads(payload)
        diagnosis = result.get("diagnosis") or {}
        summaries.append({
            "run_id": rid,
            "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "model": result.get("model"),
            "fault_type": (result.get("ground_truth") or {}).get("fault_type"),
            "root_cause_service": diagnosis.get("root_cause_service"),
            "outcome": "error" if result.get("error") else diagnosis.get("status", "unavailable"),
        })
    return {"runs": summaries, "next_offset": offset + limit if len(rows) > limit else None}


@app.get("/api/runs/{rid}")
def run_status(rid: str):
    saved = ledger().replay(rid)
    if saved:
        return {"status": "completed", "result": public_result(json.loads(saved))}
    if rid in _jobs:
        return {"status": "running", "progress": public_result(_jobs[rid])}
    raise HTTPException(404, "Run unavailable; it may have been interrupted by a restart")


@app.get("/api/replay")
def example_replay():
    path = STATIC / "offline-replay.json"
    if not path.exists():
        raise HTTPException(404, "No offline replay has been generated")
    return FileResponse(path)
