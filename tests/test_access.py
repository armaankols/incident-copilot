"""Link sessions protect both paid endpoints before admission or SDK creation."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.access as access
import app.main as main

TOKEN = "test-demo-access-token-" + "a" * 32


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "access.sqlite3"))
    def forbidden(*args):
        raise AssertionError("Access tests must not create an SDK or call a model")
    monkeypatch.setattr(main, "make_llm", forbidden)
    with TestClient(main.app, base_url="https://testserver") as test_client:
        yield test_client


def assert_no_reservations():
    with main.ledger().connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def unlock(client):
    response = client.post("/api/access", json={"token": TOKEN})
    assert response.status_code == 200
    return response


def test_public_routes_and_both_paid_routes_without_access(client):
    for path in ("/", "/api/replay", "/api/runs", "/api/config"):
        assert client.get(path).status_code == 200
    assert client.get("/api/config").json()["agent_access"] is False
    for path in ("/api/runs", "/api/investigate"):
        response = client.post(path, json={})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
    assert_no_reservations()


def test_valid_session_cookie_is_private_and_does_not_create_run(client):
    response = unlock(client)
    cookie = response.headers["set-cookie"].lower()
    for attribute in ("httponly", "secure", "samesite=strict", "path=/api", "max-age=7200"):
        assert attribute in cookie
    assert TOKEN not in cookie and TOKEN not in response.text
    config = client.get("/api/config")
    assert config.json()["agent_access"] is True
    assert config.headers["cache-control"] == "no-store"
    assert_no_reservations()


@pytest.mark.parametrize("token", ["incorrect", "", "x" * 257, "✧" * 32])
def test_invalid_access_links_never_grant_access(client, token):
    assert client.post("/api/access", json={"token": token}).status_code == 401
    assert client.get("/api/config").json()["agent_access"] is False
    assert_no_reservations()


@pytest.mark.parametrize("cookie", ["garbage", "9999999999.abc.signature", "0." + "a" * 32 + "." + "b" * 64,
                                    "x" * 200, "1000000000." + "a" * 32 + "." + "z" * 64])
def test_malformed_or_forged_cookies_fail_closed(client, cookie):
    client.cookies.set(access.COOKIE, cookie, domain="testserver.local", path="/api")
    assert client.get("/api/config").json()["agent_access"] is False
    for path in ("/api/runs", "/api/investigate"):
        assert client.post(path, json={}).status_code == 401
    assert_no_reservations()


def test_expired_sessions_and_key_rotation_revoke_access(client, monkeypatch):
    clock = {"now": 1_700_000_000}
    monkeypatch.setattr(access, "time", SimpleNamespace(time=lambda: clock["now"]))
    unlock(client)
    clock["now"] += access.SESSION_SECONDS + 1
    assert client.get("/api/config").json()["agent_access"] is False
    assert client.post("/api/runs", json={}).status_code == 401
    unlock(client)
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", "rotated-demo-token-" + "b" * 32)
    assert client.get("/api/config").json()["agent_access"] is False
    assert client.post("/api/investigate", json={}).status_code == 401
    assert_no_reservations()


@pytest.mark.parametrize("origin", ["https://unrelated.example", "http://testserver", "null", "http://["])
def test_cross_origin_unlock_and_live_requests_rejected(client, origin):
    assert client.post("/api/access", json={"token": TOKEN}, headers={"Origin": origin}).status_code == 403
    unlock(client)
    assert client.post("/api/runs", json={}, headers={"Origin": origin}).status_code == 403
    assert_no_reservations()


def test_valid_same_origin_session_still_obeys_budget_and_model_configuration(client, monkeypatch):
    assert client.post("/api/access", json={"token": TOKEN}, headers={"Origin": "https://testserver"}).status_code == 200
    monkeypatch.setattr(main, "DAILY_BUDGET_USD", .1)
    assert client.post("/api/runs", json={}, headers={"Origin": "https://testserver"}).status_code == 429
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert client.post("/api/investigate", json={}).status_code == 503
    assert_no_reservations()


@pytest.mark.parametrize("token", [None, "short-token"])
def test_missing_or_short_server_token_closes_gate(client, monkeypatch, token):
    unlock(client)
    if token is None:
        monkeypatch.delenv("DEMO_ACCESS_TOKEN")
    else:
        monkeypatch.setenv("DEMO_ACCESS_TOKEN", token)
    assert client.get("/api/config").json()["agent_access"] is False
    assert client.post("/api/runs", json={}).status_code == 401
    assert client.post("/api/access", json={"token": TOKEN}).status_code == 401
    assert_no_reservations()


def test_local_http_preview_can_use_session_cookie_without_live_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "preview.sqlite3"))
    with TestClient(main.app, base_url="http://localhost:8765") as client:
        response = unlock(client)
        assert "; secure" not in response.headers["set-cookie"].lower()
        config = client.get("/api/config").json()
        assert config["agent_access"] is True and config["live_enabled"] is False
        assert client.post("/api/runs", json={}).status_code == 503
    assert_no_reservations()
