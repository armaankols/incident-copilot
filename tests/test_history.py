"""Saved-run discovery stays read-only and omits private admission data."""
import json
import hashlib

from fastapi.testclient import TestClient

import app.main as main
from copilot.budget import Ledger


def test_page_requests_matching_script_and_revalidates_cached_assets():
    version = hashlib.sha256((main.STATIC / "demo.js").read_bytes()).hexdigest()[:16]
    with TestClient(main.app) as client:
        page = client.get("/")
        assert f'src="/static/demo.js?v={version}"' in page.text
        assert page.headers["cache-control"] == "no-cache"
        script = client.get(f"/static/demo.js?v={version}")
        assert script.status_code == 200
        assert script.content == (main.STATIC / "demo.js").read_bytes()
        assert script.headers["cache-control"] == "no-cache"
        cached = client.get(f"/static/demo.js?v={version}", headers={"If-None-Match": script.headers["etag"]})
        assert cached.status_code == 304
        assert cached.headers["cache-control"] == "no-cache"


def test_saved_history_paginates_and_reopens_without_credentials(monkeypatch, tmp_path):
    path = tmp_path / "history.sqlite3"
    monkeypatch.setenv("BUDGET_DB", str(path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(main, "make_llm", lambda *args: (_ for _ in ()).throw(AssertionError("No LLM calls")))
    ledger = Ledger(path)
    ids = []
    for number in range(3):
        rid = ledger.reserve(.1, 2, "private-visitor-hash")
        ids.append(rid)
        ledger.save_replay(rid, json.dumps({
            "run_id": rid, "model": "test-model", "trace": [{"private_large_trace": "not in summary"}],
            "ground_truth": {"fault_type": "memory_leak"},
            "diagnosis": {"status": "diagnosed", "root_cause_service": "orders"},
        }))
        ledger.settle(rid, .01)
        with ledger.connect() as db:
            db.execute("UPDATE runs SET started=? WHERE id=?", (1000 + number, rid))
    # An admitted run with no saved result should not appear as replayable.
    ledger.reserve(.1, 2, "active-visitor")
    with TestClient(main.app) as client:
        first = client.get("/api/runs?limit=2").json()
        assert [r["run_id"] for r in first["runs"]] == ids[::-1][:2]
        assert first["next_offset"] == 2
        assert first["runs"][0]["started_at"] == "1970-01-01T00:16:42+00:00"
        assert first["runs"][0]["root_cause_service"] == "orders"
        assert not any(secret in json.dumps(first) for secret in ("visitor", "reserved", "charged", "trace"))
        last = client.get("/api/runs?limit=2&offset=2").json()
        assert [r["run_id"] for r in last["runs"]] == [ids[0]]
        assert last["next_offset"] is None
        result = client.get(f"/api/runs/{ids[0]}").json()
        assert result["status"] == "completed" and result["result"]["run_id"] == ids[0]
    assert Ledger(path).saved_runs(10, 0) == ledger.saved_runs(10, 0)
    assert ledger.spent() == .03


def test_empty_failed_history_and_query_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "history.sqlite3"))
    with TestClient(main.app) as client:
        assert client.get("/api/runs").json() == {"runs": [], "next_offset": None}
        for query in ("limit=0", "limit=51", "offset=-1", "limit=invalid"):
            assert client.get(f"/api/runs?{query}").status_code == 422
        ledger = main.ledger()
        rid = ledger.reserve(.1, 2, "visitor")
        ledger.settle(rid, .1, uncertain=True)
        ledger.save_replay(rid, json.dumps({"run_id": rid, "error": "Investigation failed", "diagnosis": None}))
        run = client.get("/api/runs").json()["runs"][0]
        assert run["outcome"] == "error"
        assert run["model"] is None and run["fault_type"] is None
