"""Owner passwords gate both Sonnet routes without entering traces or storage."""
from types import SimpleNamespace
import json

from fastapi.testclient import TestClient
import pytest

import app.main as main

TOKEN = "public-demo-link-fixture-" + "a" * 32
PASSWORD = "private-owner-password-fixture"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("SONNET_PASSCODE", PASSWORD)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-fixture-not-real")
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "sonnet.sqlite3"))
    monkeypatch.setattr(main, "DAILY_BUDGET_USD", .5)
    monkeypatch.setattr(main, "make_llm", lambda *args: pytest.fail("No provider client may be created"))
    with TestClient(main.app, base_url="https://testserver") as test_client:
        assert test_client.post("/api/access", json={"token": TOKEN}).status_code == 200
        yield test_client


def no_reservations():
    with main.ledger().connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


@pytest.mark.parametrize("path", ["/api/runs", "/api/investigate"])
@pytest.mark.parametrize("password", [None, "wrong", TOKEN])
def test_missing_wrong_or_public_password_denies_sonnet_before_reservation(client, path, password):
    response = client.post(path, json={"model": main.SONNET_MODEL, "sonnet_passcode": password})
    assert response.status_code == 403
    assert "owner password" in response.json()["detail"]
    assert response.headers["cache-control"] == "no-store"
    no_reservations()


@pytest.mark.parametrize("configured", [None, "", TOKEN])
def test_unconfigured_password_and_reused_public_token_fail_closed(client, monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("SONNET_PASSCODE")
    else:
        monkeypatch.setenv("SONNET_PASSCODE", configured)
    response = client.post("/api/runs", json={"model": main.SONNET_MODEL, "sonnet_passcode": configured or PASSWORD})
    assert response.status_code == 403
    no_reservations()


@pytest.mark.parametrize("path", ["/api/runs", "/api/investigate"])
def test_owner_password_alone_cannot_bypass_public_link_or_origin_checks(client, path):
    response = client.post(path, json={"model": main.SONNET_MODEL, "sonnet_passcode": PASSWORD},
                           headers={"Origin": "https://other.example"})
    assert response.status_code == 403
    client.cookies.clear()
    response = client.post(path, content=b'{"sonnet_passcode":', headers={"Content-Type": "application/json"})
    assert response.status_code == 401
    no_reservations()


@pytest.mark.parametrize("path", ["/api/runs", "/api/investigate"])
@pytest.mark.parametrize("password", [PASSWORD, "privaté owner password"])
def test_owner_sonnet_starts_at_49_cents_and_password_never_reaches_execution_or_replays(client, monkeypatch, path, password, caplog):
    monkeypatch.setenv("SONNET_PASSCODE", password)
    ledger = main.ledger()
    ledger.settle(ledger.reserve(.42, .5, "earlier"), .49)
    sentinel = object()
    models = []
    def make_llm(model):
        models.append(model)
        return sentinel
    monkeypatch.setattr(main, "make_llm", make_llm)
    original_execute = main.execute
    async def check_execution(rid, req):
        assert req.sonnet_passcode is None
        return await original_execute(rid, req)
    monkeypatch.setattr(main, "execute", check_execution)
    async def fake_scenario(scenario, llm, max_steps, progress):
        assert llm is sentinel and max_steps == 12
        progress["usage"] = {"input_tokens": 20000}
        return {"cost_usd": .06, "diagnosis": None}
    monkeypatch.setattr(main, "run_scenario", fake_scenario)
    response = client.post(path, json={"model": main.SONNET_MODEL, "sonnet_passcode": password})
    assert response.status_code == (202 if path == "/api/runs" else 200)
    assert models == [main.SONNET_MODEL]
    assert ledger.spent() == pytest.approx(.55)
    with ledger.connect() as db:
        row = db.execute("SELECT id,reserved,charged,active FROM runs WHERE visitor!='earlier'").fetchone()
        assert row[1:] == pytest.approx((1.26, .06, 0))
        replay = db.execute("SELECT payload FROM replays WHERE id=?", (row[0],)).fetchone()[0]
    assert password not in replay and "sonnet_passcode" not in replay
    assert password not in response.text and password not in caplog.text
    for followup in ("/api/config", "/api/runs", "/api/runs/" + row[0]):
        assert password not in client.get(followup).text
    blocked = client.post(path, json={"model": main.SONNET_MODEL, "sonnet_passcode": password})
    assert blocked.status_code == 429
    assert "Daily API start limit reached" in blocked.json()["detail"]
    assert models == [main.SONNET_MODEL]


def test_sonnet_password_attempt_limit_is_shared_by_both_paid_routes(client, monkeypatch):
    monkeypatch.setattr("copilot.budget.time", SimpleNamespace(time=lambda: 120.0))
    for number in range(20):
        path = "/api/runs" if number % 2 else "/api/investigate"
        assert client.post(path, json={"model": main.SONNET_MODEL, "sonnet_passcode": "wrong"}).status_code == 403
    response = client.post("/api/runs", json={"model": main.SONNET_MODEL, "sonnet_passcode": PASSWORD})
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    no_reservations()


def test_password_validation_and_model_repr_are_redacted(client):
    secret = PASSWORD + "x" * 257
    response = client.post("/api/runs", json={"model": main.SONNET_MODEL, "sonnet_passcode": secret})
    assert response.status_code == 422
    assert PASSWORD not in response.text and "input" not in response.text
    req = main.InvestigateRequest(model=main.SONNET_MODEL, sonnet_passcode=PASSWORD)
    assert PASSWORD not in repr(req)
    assert PASSWORD not in req.model_dump_json()
    assert PASSWORD not in json.dumps(client.get("/api/config").json())
    no_reservations()
