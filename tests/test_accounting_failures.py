"""Real SDK/MCP plumbing with mocked HTTP: no paid provider calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

import app.main as main
from copilot.budget import AdmissionDenied, Ledger
from copilot.errors import CREDIT_MESSAGE
from copilot.llm import AnthropicLLM
from copilot.pricing import DEFAULT_MODEL


@pytest.mark.parametrize("prior_success", [False, True])
@pytest.mark.parametrize("reject_at", ["count", "generation"])
def test_credit_rejection_releases_unused_hold_but_retains_reported_usage(monkeypatch, tmp_path, prior_success, reject_at):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "credit.sqlite3"))
    paths = []
    successful = 0
    def response(request):
        nonlocal successful
        paths.append(request.url.path)
        count = request.url.path.endswith("count_tokens")
        reject = (not prior_success or successful > 0) and (count if reject_at == "count" else not count)
        if reject:
            return httpx2.Response(400, json={"type": "error", "error": {
                "type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}}, request=request)
        if count:
            return httpx2.Response(200, json={"input_tokens": 100}, request=request)
        successful += 1
        return httpx2.Response(200, json={"id": "msg_offline", "type": "message", "role": "assistant",
            "model": DEFAULT_MODEL, "content": [{"type": "tool_use", "id": "tool", "name": "list_services", "input": {}}],
            "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 1000, "output_tokens": 100}}, request=request)
    async def check():
        llm = object.__new__(AnthropicLLM)
        llm.model, llm.max_tokens, llm.max_input_tokens = DEFAULT_MODEL, 1000, 24000
        llm.client = anthropic.AsyncAnthropic(api_key="offline-fixture-not-real", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(response)))
        monkeypatch.setattr(main, "make_llm", lambda model: llm)
        try:
            rid = main.ledger().reserve(.42, .5, "offline-credit-fixture")
            result = await main.execute(rid, main.InvestigateRequest(fault_type="memory_leak"))
            assert result["error"].startswith(CREDIT_MESSAGE)
            assert "credit balance is too low" not in result["error"]
            assert result["error_code"] == "provider_credit_unavailable"
            assert result["billing_uncertain"] is False
            expected = .0015 if prior_success else 0
            assert result["cost_usd"] == pytest.approx(expected)
            assert main.ledger().spent() == pytest.approx(expected)
            assert result["model_calls"] == (2 if prior_success else 1)
            assert main.ledger().reserve(.42, .5, "next-visitor")
            assert paths
        finally:
            await llm.client.close()
    asyncio.run(check())


@pytest.mark.parametrize("failure", ["timeout", "unrelated_400", "server_503"])
def test_unconfirmed_provider_failures_keep_full_hold(monkeypatch, tmp_path, failure):
    monkeypatch.setenv("BUDGET_DB", str(tmp_path / "uncertain.sqlite3"))
    def response(request):
        if request.url.path.endswith("count_tokens"):
            return httpx2.Response(200, json={"input_tokens": 100}, request=request)
        if failure == "timeout":
            raise httpx2.ReadTimeout("dummy network timeout", request=request)
        return httpx2.Response(400 if failure == "unrelated_400" else 503,
            json={"type": "error", "error": {"type": "invalid_request_error", "message": "dummy unrelated rejection"}}, request=request)
    async def check():
        llm = object.__new__(AnthropicLLM)
        llm.model, llm.max_tokens, llm.max_input_tokens = DEFAULT_MODEL, 1000, 24000
        llm.client = anthropic.AsyncAnthropic(api_key="offline-fixture-not-real", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(response)))
        monkeypatch.setattr(main, "make_llm", lambda model: llm)
        try:
            rid = main.ledger().reserve(.42, .5, "offline-uncertain-fixture")
            result = await main.execute(rid, main.InvestigateRequest())
            assert result["billing_uncertain"] is True
            assert result["cost_usd"] == 0
            assert main.ledger().spent() == .42
            assert not result["error"].startswith(CREDIT_MESSAGE)
        finally:
            await llm.client.close()
    asyncio.run(check())


def test_cross_midnight_hold_and_settlement_do_not_leave_budget_gap(monkeypatch, tmp_path):
    ledger = Ledger(tmp_path / "midnight.sqlite3")
    day = {"value": "2026-10-13"}
    monkeypatch.setattr(Ledger, "day", staticmethod(lambda: day["value"]))
    rid = ledger.reserve(.42, .5, "visitor")
    day["value"] = "2026-10-14"
    with pytest.raises(AdmissionDenied):
        ledger.reserve(.42, .5, "visitor")
    def settle():
        Ledger(ledger.path).settle(rid, .42)
    def reserve():
        try:
            return Ledger(ledger.path).reserve(.42, .5, "other")
        except AdmissionDenied:
            return None
    with ThreadPoolExecutor(2) as pool:
        settled = pool.submit(settle)
        admitted = pool.submit(reserve)
        settled.result()
        assert admitted.result() is None
    assert ledger.spent() == .42
    day["value"] = "2026-10-15"
    ledger.settle(rid, .1)  # Idempotent settlement cannot move an old charge.
    assert ledger.spent() == 0
    with ledger.connect() as db:
        assert db.execute("SELECT day,charged FROM runs WHERE id=?", (rid,)).fetchone() == ("2026-10-14", .42)


def test_cross_midnight_partial_usage_releases_only_unused_reservation(monkeypatch, tmp_path):
    ledger = Ledger(tmp_path / "partial.sqlite3")
    monkeypatch.setattr(Ledger, "day", staticmethod(lambda: "2026-10-13"))
    rid = ledger.reserve(.42, .5, "visitor")
    monkeypatch.setattr(Ledger, "day", staticmethod(lambda: "2026-10-14"))
    ledger.settle(rid, .03)
    assert ledger.spent() == .03
    assert ledger.reserve(.42, .5, "other")
