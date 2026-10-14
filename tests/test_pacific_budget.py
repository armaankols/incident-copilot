"""Pacific calendar-day admission, DST resets and a lossless UTC-ledger upgrade."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.main as main
from copilot.budget import AdmissionDenied, Ledger, PACIFIC


def clock(monkeypatch, value):
    monkeypatch.setattr(Ledger, "now", staticmethod(lambda: datetime.fromisoformat(value)))


@pytest.mark.parametrize("instant,day,reset,hours", [
    ("2026-10-14T00:00:00+00:00", "2026-10-13", "2026-10-14T00:00:00-07:00", 24),
    ("2026-10-14T07:00:00+00:00", "2026-10-14", "2026-10-15T00:00:00-07:00", 24),
    ("2026-03-08T08:00:00+00:00", "2026-03-08", "2026-03-09T00:00:00-07:00", 23),
    ("2026-11-01T07:00:00+00:00", "2026-11-01", "2026-11-02T00:00:00-08:00", 25),
])
def test_pacific_dates_and_dst_resets(monkeypatch, tmp_path, instant, day, reset, hours):
    clock(monkeypatch, instant)
    ledger = Ledger(tmp_path / "budget.sqlite3")
    assert ledger.day() == day
    status = ledger.budget_status()
    assert status["budget_date"] == day
    assert status["budget_timezone"] == "America/Los_Angeles"
    assert status["budget_resets_at"] == reset
    # Use ZoneInfo at both midnights, not a fixed PST/PDT offset.
    period_start = datetime.fromisoformat(day).replace(tzinfo=PACIFIC)
    length = datetime.fromisoformat(reset).astimezone(timezone.utc) - period_start.astimezone(timezone.utc)
    assert length == timedelta(hours=hours)


def test_utc_midnight_does_not_reset_but_pacific_midnight_does(monkeypatch, tmp_path):
    clock(monkeypatch, "2026-10-13T23:59:59+00:00")
    ledger = Ledger(tmp_path / "budget.sqlite3")
    rid = ledger.reserve(.42, .5, "first")
    ledger.settle(rid, .198665)
    clock(monkeypatch, "2026-10-14T00:00:00+00:00")
    assert ledger.spent() == .198665
    with pytest.raises(AdmissionDenied):
        ledger.reserve(.42, .5, "second")
    clock(monkeypatch, "2026-10-14T07:00:00+00:00")
    assert ledger.spent() == 0
    assert ledger.reserve(.42, .5, "second")


def test_active_hold_and_settlement_cross_pacific_midnight(monkeypatch, tmp_path):
    clock(monkeypatch, "2026-10-14T06:59:59+00:00")
    ledger = Ledger(tmp_path / "budget.sqlite3")
    rid = ledger.reserve(.42, .5, "first")
    clock(monkeypatch, "2026-10-14T07:00:00+00:00")
    with pytest.raises(AdmissionDenied):
        Ledger(ledger.path).reserve(.42, .5, "second")
    ledger.settle(rid, .42)
    assert ledger.budget_status()["spent_today_usd"] == .42
    with pytest.raises(AdmissionDenied):
        ledger.reserve(.42, .5, "second")


def legacy(path, rows):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, day TEXT, visitor TEXT, started REAL, reserved REAL, charged REAL, active INTEGER)")
        db.execute("CREATE TABLE replays (id TEXT PRIMARY KEY, payload TEXT)")
        for rid, day, started, charge, active in rows:
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)", (rid, day, "private", datetime.fromisoformat(started).timestamp(), .42, charge, active))
            db.execute("INSERT INTO replays VALUES (?,?)", (rid, json.dumps({"run_id": rid, "cost_usd": charge})))


def test_migrate_four_legacy_runs_atomically_and_once(monkeypatch, tmp_path):
    path = tmp_path / "legacy.sqlite3"
    rows = [
        ("first", "2026-10-13", "2026-10-13T19:10:57+00:00", .060967, 0),
        ("second", "2026-10-13", "2026-10-13T20:15:12+00:00", .029711, 0),
        ("third", "2026-10-14", "2026-10-14T03:54:56+00:00", .032945, 0),
        ("fourth", "2026-10-14", "2026-10-14T03:57:49+00:00", .075042, 0),
    ]
    legacy(path, rows)
    with sqlite3.connect(path) as db:
        original_runs = db.execute("SELECT id,visitor,started,reserved,charged,active FROM runs ORDER BY id").fetchall()
        original_replays = db.execute("SELECT * FROM replays ORDER BY id").fetchall()
    clock(monkeypatch, "2026-10-14T04:15:00+00:00")
    ledger = Ledger(path)
    assert ledger.budget_status()["spent_today_usd"] == .198665
    with pytest.raises(AdmissionDenied):
        ledger.reserve(.42, .5, "new")
    with ledger.connect() as db:
        assert db.execute("SELECT id,visitor,started,reserved,charged,active FROM runs ORDER BY id").fetchall() == original_runs
        assert db.execute("SELECT * FROM replays ORDER BY id").fetchall() == original_replays
        assert db.execute("SELECT DISTINCT day FROM runs").fetchall() == [("2026-10-13",)]
        assert dict(db.execute("SELECT * FROM legacy_utc_days")) == {r[0]: r[1] for r in rows}
    clock(monkeypatch, "2026-10-14T08:00:00+00:00")
    assert Ledger(path).spent() == 0
    with ledger.connect() as db:
        assert db.execute("SELECT DISTINCT day FROM runs").fetchall() == [("2026-10-13",)]


def test_ambiguous_legacy_settlement_fails_closed_without_partial_migration(monkeypatch, tmp_path):
    path = tmp_path / "ambiguous.sqlite3"
    legacy(path, [("safe", "2026-10-13", "2026-10-13T19:00:00+00:00", .1, 0),
                  ("ambiguous", "2026-10-14", "2026-10-14T03:00:00+00:00", .1, 0)])
    clock(monkeypatch, "2026-10-14T08:00:00+00:00")
    with pytest.raises(ValueError, match="reviewed Pacific day assignments"):
        Ledger(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id,day FROM runs ORDER BY id").fetchall() == [("ambiguous", "2026-10-14"), ("safe", "2026-10-13")]
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='ledger_settings'").fetchall()


def test_legacy_active_hold_remains_reserved_after_migration(monkeypatch, tmp_path):
    path = tmp_path / "active.sqlite3"
    legacy(path, [("active", "2026-10-13", "2026-10-13T19:00:00+00:00", 0, 1)])
    clock(monkeypatch, "2026-10-14T08:00:00+00:00")
    ledger = Ledger(path)
    with pytest.raises(AdmissionDenied):
        ledger.reserve(.42, .5, "new")
    ledger.settle("active", .42)
    assert ledger.spent() == .42


def test_config_amount_and_pacific_period_match(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "api.sqlite3"))
    clock(monkeypatch, "2026-10-14T04:00:00+00:00")
    ledger = main.ledger()
    ledger.settle(ledger.reserve(.42, .5, "visitor"), .198665)
    with TestClient(main.app) as client:
        config = client.get("/api/config").json()
    assert config["spent_today_usd"] == .198665
    assert config["budget_date"] == "2026-10-13"
    assert config["budget_timezone"] == "America/Los_Angeles"
    assert config["budget_resets_at"] == "2026-10-14T00:00:00-07:00"
