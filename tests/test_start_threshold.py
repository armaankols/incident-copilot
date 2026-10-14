"""Start below the daily threshold, finish above it, then reject further runs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi.testclient import TestClient
import pytest

import app.main as main
from copilot.budget import AdmissionDenied, Ledger
from copilot.pricing import DEFAULT_MODEL


def seed(ledger, charge):
    rid = ledger.reserve(.42, .5, "earlier")
    ledger.settle(rid, charge)


@pytest.mark.parametrize("spent", [.198665, .49, .4999999])
def test_start_is_allowed_below_threshold_even_without_room_for_full_run(tmp_path, spent):
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    seed(ledger, spent)
    assert ledger.reserve(.42, .5, "next", start_threshold=True)
    assert ledger.spent() == spent  # Reservation is not reported spend.


@pytest.mark.parametrize("spent", [.5, .51])
def test_start_is_denied_at_or_above_threshold(tmp_path, spent):
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    seed(ledger, spent)
    with pytest.raises(AdmissionDenied, match="Daily API start limit reached"):
        ledger.reserve(.42, .5, "next", start_threshold=True)


def test_final_run_can_cross_threshold_but_no_further_run_starts(tmp_path):
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    seed(ledger, .49)
    rid = ledger.reserve(.42, .5, "final", start_threshold=True)
    ledger.settle(rid, .075)
    assert ledger.spent() == pytest.approx(.565)
    with pytest.raises(AdmissionDenied, match="Daily API start limit reached"):
        Ledger(ledger.path).reserve(.42, .5, "next", start_threshold=True)


def test_racing_starts_near_threshold_admit_only_one(tmp_path):
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    seed(ledger, .49)
    def attempt(number):
        try:
            return Ledger(ledger.path).reserve(.42, .5, str(number), concurrency=20, start_threshold=True)
        except AdmissionDenied:
            return None
    with ThreadPoolExecutor(max_workers=20) as pool:
        admitted = [rid for rid in pool.map(attempt, range(20)) if rid]
    assert len(admitted) == 1


@pytest.mark.parametrize("spent", [0, .49])
def test_start_threshold_allows_larger_model_below_daily_threshold(tmp_path, spent):
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    seed(ledger, spent)
    assert ledger.reserve(1.26, .5, "owner-sonnet", start_threshold=True)


def test_start_threshold_preserves_concurrency(tmp_path):
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    ledger.reserve(.42, .5, "first", concurrency=1, start_threshold=True)
    with pytest.raises(AdmissionDenied, match="capacity"):
        ledger.reserve(.42, .5, "second", concurrency=1, start_threshold=True)


def test_prior_day_hold_remains_counted_and_only_confirmed_unused_funds_release(monkeypatch, tmp_path):
    clock = {"now": datetime.fromisoformat("2026-10-14T06:59:59+00:00")}
    monkeypatch.setattr(Ledger, "now", staticmethod(lambda: clock["now"]))
    ledger = Ledger(tmp_path / "threshold.sqlite3")
    unfinished = ledger.reserve(.42, .5, "first", start_threshold=True)
    second = ledger.reserve(.42, .5, "second", start_threshold=True)
    clock["now"] = datetime.fromisoformat("2026-10-14T07:00:00+00:00")
    ledger.settle(second, .1)
    with pytest.raises(AdmissionDenied, match="reserved"):
        Ledger(ledger.path).reserve(.42, .5, "third", start_threshold=True)
    ledger.settle(unfinished, 0)  # e.g. confirmed provider credit rejection.
    assert ledger.reserve(.42, .5, "third", start_threshold=True)


@pytest.mark.parametrize("path", ["/api/runs", "/api/investigate"])
def test_both_paid_endpoints_start_at_49_cents_with_mocked_model_and_stop_afterwards(monkeypatch, tmp_path, path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-fixture-not-real")
    token = "offline-access-fixture-" + "x" * 32
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", token)
    monkeypatch.setattr(main, "DAILY_BUDGET_USD", .5)
    seed(main.ledger(), .49)
    calls = []
    sentinel = object()
    monkeypatch.setattr(main, "make_llm", lambda model: sentinel)
    async def fake_scenario(scenario, llm, max_steps, progress):
        assert llm is sentinel
        calls.append(True)
        progress["usage"] = {"input_tokens": 20000}
        return {"model": DEFAULT_MODEL, "cost_usd": .02, "diagnosis": None}
    monkeypatch.setattr(main, "run_scenario", fake_scenario)
    with TestClient(main.app, base_url="https://testserver") as client:
        assert client.post("/api/access", json={"token": token}).status_code == 200
        response = client.post(path, json={})
        assert response.status_code == (202 if path == "/api/runs" else 200)
        assert main.ledger().spent() == pytest.approx(.51)
        config = client.get("/api/config").json()
        assert config["budget_policy"] == "start_threshold"
        assert config["spent_today_usd"] == .51
        response = client.post(path, json={})
        assert response.status_code == 429
        assert "Daily API start limit reached" in response.json()["detail"]
        assert len(calls) == 1


def test_sonnet_without_owner_password_is_blocked_before_sdk_creation(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "sonnet.sqlite3"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-fixture-not-real")
    token = "offline-access-fixture-" + "x" * 32
    monkeypatch.setenv("DEMO_ACCESS_TOKEN", token)
    monkeypatch.setattr(main, "DAILY_BUDGET_USD", .5)
    monkeypatch.setattr(main, "make_llm", lambda *args: pytest.fail("No SDK creation allowed"))
    with TestClient(main.app, base_url="https://testserver") as client:
        assert client.post("/api/access", json={"token": token}).status_code == 200
        for path in ("/api/runs", "/api/investigate"):
            response = client.post(path, json={"model": "claude-sonnet-4-6"})
            assert response.status_code == 403
            assert "owner password" in response.json()["detail"]
    with main.ledger().connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
