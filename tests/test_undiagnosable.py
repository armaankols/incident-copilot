"""Selectable incomplete telemetry, using the existing challenge-suite rules."""
import asyncio
import hashlib
import json
import time

from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session
import pytest

import app.main as main
from copilot.llm import ScriptedLLM
from copilot.mcp_server import build_server
from copilot.sim import FAULT_TYPES, SERVICES, generate_undiagnosable
from evals.cases import scenarios


@pytest.mark.parametrize("seed", [1, 7, 93251])
def test_missing_telemetry_is_reproducible_and_all_diagnostic_checks_remain_unknown(seed):
    sc = generate_undiagnosable(seed)
    assert sc.__dict__ == generate_undiagnosable(seed).__dict__
    assert sc.fault_type == "insufficient_evidence" and sc.root_service is None
    assert set(sc.metrics) == {"gateway"}
    assert sc.deploys == [] and all(row[1] == "gateway" for row in sc.logs)
    assert "insufficient_evidence" not in sc.alert and "undiagnosable" not in sc.alert.lower()
    async def check():
        async with create_connected_server_and_client_session(build_server(sc, use_rag=False)) as session:
            for service in SERVICES:
                for fault in FAULT_TYPES:
                    name = "check_change" if fault in ("bad_deploy", "config_error") else "check_certificate" if fault == "cert_expiry" else "check_fault"
                    args = {"service": service, **({} if name == "check_certificate" else {"fault_type": fault})}
                    response = await session.call_tool(name, args)
                    assert not response.isError
                    assessment = json.loads("\n".join(block.text for block in response.content if hasattr(block, "text")))
                    assert assessment["status"] == "unknown", (seed, service, fault, assessment)
    asyncio.run(check())


def test_extraction_preserves_the_six_existing_v2_redacted_benchmark_snapshots():
    # Preserve the pre-extraction snapshot at nanounit precision. Python's
    # Gaussian sampler can differ by a few floating-point bits across libm builds.
    def canonical(value):
        if isinstance(value, float):
            return round(value, 9)
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(item) for item in value]
        return value

    data = [sc.__dict__ for sc in scenarios(6, 0, "correlated-v2", offset=18)]
    digest = hashlib.sha256(json.dumps(canonical(data), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == "280d62f3f804ebe21ba751925b12801c77d218033d2e7973cd82bceccedd336f"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "web.sqlite3"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-fixture-not-real")
    token = "demo-access-fixture-" + "x" * 32
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", token)
    monkeypatch.setattr(main, "DAILY_BUDGET_USD", .5)
    def make_llm(model):
        return ScriptedLLM([
            [{"type": "tool_use", "id": "metrics", "name": "query_metrics", "input": {"service": "orders", "metric": "error_rate"}},
             {"type": "tool_use", "id": "deploys", "name": "get_recent_deploys", "input": {}}],
            [{"type": "tool_use", "id": "abstain", "name": "submit_diagnosis", "input": {
                "status": "insufficient_evidence", "root_cause_service": None, "fault_type": None,
                "evidence": [], "action": None, "target": None}}],
        ], model=model)
    monkeypatch.setattr(main, "make_llm", make_llm)
    with TestClient(main.app, base_url="https://testserver") as browser:
        assert browser.post("/api/access", json={"token": token}).status_code == 200
        yield browser


@pytest.mark.parametrize("path", ["/api/runs", "/api/investigate"])
def test_both_web_routes_run_missing_telemetry_through_real_mcp_with_scripted_responses(client, path):
    config = client.get("/api/config").json()
    assert config["fault_types"] == [*FAULT_TYPES, "insufficient_evidence"]
    response = client.post(path, json={"fault_type": "insufficient_evidence"})
    if path == "/api/runs":
        assert response.status_code == 202
        rid = response.json()["run_id"]
        for _ in range(100):
            status = client.get("/api/runs/" + rid).json()
            if status["status"] == "completed":
                result = status["result"]
                break
            time.sleep(.02)
        else:
            pytest.fail("Scripted background run did not finish")
    else:
        assert response.status_code == 200
        result = response.json()
    assert result["error"] is None
    assert result["ground_truth"] == {"root_service": None, "fault_type": "insufficient_evidence"}
    assert result["diagnosis"]["status"] == "insufficient_evidence"
    assert result["diagnosis"]["action"] is None and result["diagnosis"]["target"] is None
    assert result["grade"]["both_ok"] and result["grade"]["abstained"]
    assert result["termination_reason"] == "model_submission"
    assert result["model_calls"] == 2
    outputs = [event["output"] for event in result["trace"] if event["type"] == "tool_result"]
    assert len(outputs) == 2 and all("UNAVAILABLE" in output for output in outputs)
    history = client.get("/api/runs").json()["runs"]
    assert history[0]["fault_type"] == "insufficient_evidence"
    assert history[0]["outcome"] == "insufficient_evidence"


def test_new_case_keeps_access_and_input_validation_guards(client):
    assert client.post("/api/runs", json={"fault_type": "unknown"}).status_code == 400
    client.cookies.clear()
    assert client.post("/api/runs", json={"fault_type": "insufficient_evidence"}).status_code == 401
    with main.ledger().connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
