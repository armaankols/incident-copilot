"""Regression checks for the audited request, proxy and public-error boundaries."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

from fastapi import Request
from fastapi.testclient import TestClient
import pytest

import app.main as main
import app.security as security
import copilot.runner as runner
from copilot.budget import Ledger
from copilot.llm import ScriptedLLM

TOKEN = "security-regression-token-" + "a" * 32


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "security.sqlite3"))
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-real")
    monkeypatch.setattr(main, "make_llm", lambda model: ScriptedLLM([[]], model=model))
    with TestClient(main.app, base_url="https://testserver") as client:
        yield client


def test_large_bodies_and_validation_input_are_not_reflected(client):
    response = client.post("/api/access", json={"token": "x" * (2 * 1024 * 1024)})
    assert response.status_code == 413 and len(response.content) < 200
    secret = "dummy-private-input-that-must-not-be-reflected"
    response = client.post("/api/access", json={"token": {"secret": secret}})
    assert response.status_code == 422 and secret not in response.text
    assert "input" not in response.json()["detail"][0]
    assert client.post("/api/access", json={"token": "x" * 257}).status_code == 422


def test_live_access_checked_before_json_parsing(client):
    for path in ("/api/runs", "/api/investigate"):
        response = client.post(path, content=b"not valid JSON", headers={"Content-Type": "application/json"})
        assert response.status_code == 401
    with main.ledger().connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_body_limit_counts_chunks_without_trusting_content_length():
    async def exercise(declared_length):
        called = False
        async def downstream(scope, receive, send):
            nonlocal called
            called = True
        class Unlimited:
            def allow_request(self, buckets):
                return 0
        guard = security.RequestGuard(downstream, Unlimited)
        headers = [] if declared_length is None else [(b"content-length", declared_length)]
        scope = {"type": "http", "method": "POST", "path": "/api/access", "headers": headers,
                 "client": ("192.0.2.1", 123), "scheme": "https", "server": ("testserver", 443)}
        messages = iter([{"type": "http.request", "body": b"a" * 4096, "more_body": True},
                         {"type": "http.request", "body": b"b" * 4097, "more_body": False}])
        async def receive():
            return next(messages)
        sent = []
        async def send(message):
            sent.append(message)
        await guard(scope, receive, send)
        assert not called and sent[0]["status"] == 413
    asyncio.run(exercise(None))
    asyncio.run(exercise(b"1"))


def test_exact_body_boundary_preserves_normal_requests(client):
    body = json.dumps({"token": TOKEN}).encode()
    response = client.post("/api/access", content=body + b" " * (security.MAX_BODY_BYTES - len(body)),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    response = client.post("/api/runs", json={"model": "x" * 65})
    assert response.status_code == 422


def test_access_throttle_returns_retry_after_without_reserving_money(client, monkeypatch):
    monkeypatch.setattr(security, "ACCESS_REQUESTS_PER_MINUTE", 2)
    assert client.post("/api/access", json={"token": "wrong"}).status_code == 401
    assert client.post("/api/access", json={"token": "wrong"}).status_code == 401
    response = client.post("/api/access", json={"token": TOKEN})
    assert response.status_code == 429 and 1 <= int(response.headers["Retry-After"]) <= 60
    with main.ledger().connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_public_read_quota_cannot_be_reset_with_ip_headers(client, monkeypatch):
    monkeypatch.setattr(security, "REQUESTS_PER_MINUTE", 3)
    monkeypatch.setenv("TRUST_FLY_PROXY", "1")
    monkeypatch.setenv("FLY_APP_NAME", "incident-copilot")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "192.0.2.1/32")
    monkeypatch.setattr("copilot.budget.time", SimpleNamespace(time=lambda: 120.0))
    for number in range(3):
        assert client.get("/api/config", headers={"Fly-Client-IP": f"198.51.100.{number}"}).status_code == 200
    assert client.get("/api/config", headers={"Fly-Client-IP": "198.51.100.10"}).status_code == 429


def test_incomplete_body_times_out_before_parsing(monkeypatch):
    original_wait_for = asyncio.wait_for
    monkeypatch.setattr(asyncio, "wait_for", lambda operation, timeout: original_wait_for(operation, .01))
    async def exercise():
        class Unlimited:
            def allow_request(self, buckets):
                return 0
        async def downstream(*args):
            raise AssertionError("Incomplete body must not reach the app")
        async def receive():
            await asyncio.sleep(1)
        sent = []
        async def send(message):
            sent.append(message)
        scope = {"type": "http", "method": "POST", "path": "/api/access", "headers": [],
                 "client": ("192.0.2.1", 123)}
        await security.RequestGuard(downstream, Unlimited)(scope, receive, send)
        assert sent[0]["status"] == 408
    asyncio.run(exercise())


def test_request_quota_is_atomic_durable_and_expires(tmp_path, monkeypatch):
    path = tmp_path / "requests.sqlite3"
    clock = SimpleNamespace(time=lambda: 120.0)
    monkeypatch.setattr("copilot.budget.time", clock)
    Ledger(path)
    def attempt(_):
        return Ledger(path).allow_request([("all", 7)])
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(attempt, range(24)))
    assert results.count(0) == 7
    assert Ledger(path).allow_request([("all", 7)]) == 60
    clock.time = lambda: 180.0
    assert Ledger(path).allow_request([("all", 7)]) == 0
    with Ledger(path).connect() as db:
        assert db.execute("SELECT COUNT(*) FROM request_limits").fetchone()[0] == 1


def request(peer, values):
    return Request({"type": "http", "client": (peer, 123),
                    "headers": [(b"fly-client-ip", value.encode()) for value in values]})


def test_forwarded_ip_needs_fly_runtime_and_trusted_peer(monkeypatch):
    monkeypatch.setenv("TRUST_FLY_PROXY", "1")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "192.0.2.0/24")
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    assert security.client_ip(request("192.0.2.1", ["198.51.100.1"])) == "192.0.2.1"
    monkeypatch.setenv("FLY_APP_NAME", "incident-copilot")
    assert security.client_ip(request("203.0.113.1", ["198.51.100.1"])) == "203.0.113.1"
    assert security.client_ip(request("192.0.2.1", ["198.51.100.1"])) == "198.51.100.1"
    for values in (["198.51.100.1, 198.51.100.2"], ["garbage"], ["198.51.100.1", "198.51.100.2"], []):
        assert security.client_ip(request("192.0.2.1", values)) == "192.0.2.1"
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "")
    assert security.client_ip(request("192.0.2.1", ["198.51.100.1"])) == "192.0.2.1"


def test_equivalent_ipv6_addresses_share_visitor_identity(monkeypatch):
    monkeypatch.delenv("TRUST_FLY_PROXY", raising=False)
    assert security.visitor_id(request("2001:db8::1", [])) == security.visitor_id(request("2001:0db8:0:0:0:0:0:1", []))


def test_failure_has_reference_without_internal_details_in_public_replay(client, monkeypatch, caplog):
    detail = "audit-dummy-secret /srv/runbooks/private-file.md"
    def fail(*args, **kwargs):
        raise PermissionError(detail)
    monkeypatch.setattr(runner, "build_server", fail)
    assert client.post("/api/access", json={"token": TOKEN}).status_code == 200
    result = client.post("/api/investigate", json={}).json()
    assert result["error"].startswith("Investigation failed (reference:")
    client.cookies.clear()
    public = client.get("/api/runs/" + result["run_id"])
    assert public.status_code == 200 and detail not in public.text and detail not in caplog.text
    assert "exception_type=PermissionError" in caplog.text


def test_legacy_replay_error_is_hidden_without_rewriting_storage(client):
    payload = json.dumps({"run_id": "legacy", "error": "PermissionError: private-file /srv/internal"})
    main.ledger().save_replay("legacy", payload)
    public = client.get("/api/runs/legacy")
    assert public.json()["result"]["error"] == "Investigation failed"
    assert "private-file" not in public.text
    assert main.ledger().replay("legacy") == payload


def test_trailing_slash_never_redirects_access_token_to_http(client):
    # The app sees HTTP behind TLS termination with proxy rewriting disabled.
    with TestClient(main.app, base_url="http://testserver", follow_redirects=False) as behind_proxy:
        for path in ("/api/access/", "/api/runs/", "/api/investigate/"):
            response = behind_proxy.post(path, json={"token": TOKEN})
            assert response.status_code == 404
            assert "location" not in response.headers


def test_health_quota_is_independent_of_exhausted_public_buckets(client, monkeypatch):
    monkeypatch.setattr(security, "GLOBAL_REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr(security, "REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr("copilot.budget.time", SimpleNamespace(time=lambda: 120.0))
    assert client.get("/api/config").status_code == 200
    assert client.get("/api/config").status_code == 200
    assert client.get("/api/config").status_code == 429
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").status_code == 429  # Own quota remains bounded.


def test_mcp_error_results_are_redacted_before_replay_and_model(client, monkeypatch, caplog):
    from mcp.server.fastmcp import FastMCP
    from copilot.diagnosis import insufficient
    detail = "review-dummy-private-file /srv/private-placeholder"
    def bad_server(*args, **kwargs):
        server = FastMCP("failing-tool-test")
        @server.tool()
        def list_services() -> str:
            raise PermissionError(detail)
        return server
    script = [[dict(type="tool_use", id="tool", name="list_services", input={})],
              [dict(type="tool_use", id="finish", name="submit_diagnosis", input=insufficient())]]
    class InspectingLLM(ScriptedLLM):
        async def complete(self, system, messages, tools, **kwargs):
            assert detail not in json.dumps(messages)
            return await super().complete(system, messages, tools, **kwargs)
    monkeypatch.setattr(runner, "build_server", bad_server)
    monkeypatch.setattr(main, "make_llm", lambda model: InspectingLLM(script, model=model))
    assert client.post("/api/access", json={"token": TOKEN}).status_code == 200
    result = client.post("/api/investigate", json={}).json()
    assert result["error"] is None
    assert detail not in json.dumps(result) and detail not in caplog.text
    assert any("reference:" in event.get("output", "") for event in result["trace"])
    client.cookies.clear()
    assert detail not in client.get("/api/runs/" + result["run_id"]).text


def test_legacy_and_running_trace_errors_sanitized_without_mutation(client):
    result = {"run_id": "legacy-trace", "error": None, "trace": [
        {"type": "tool_result", "output": "ERROR: Error executing tool: /srv/private-placeholder"},
        {"type": "tool_result", "output": "normal synthetic evidence"},
    ]}
    payload = json.dumps(result)
    main.ledger().save_replay("legacy-trace", payload)
    assert "private-placeholder" not in client.get("/api/runs/legacy-trace").text
    assert main.ledger().replay("legacy-trace") == payload
    main._jobs["running-trace"] = result
    try:
        response = client.get("/api/runs/running-trace")
        assert "private-placeholder" not in response.text
        assert "normal synthetic evidence" in response.text
        assert main._jobs["running-trace"] == json.loads(payload)
    finally:
        main._jobs.pop("running-trace")
