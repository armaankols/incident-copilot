import asyncio

from copilot.llm import ScriptedLLM
from copilot.retrieval import get_index
from copilot.runner import baseline_latest_deploy, grade, run_scenario
from copilot.diagnosis import ACTIONS, insufficient
from copilot.sim import FAULT_TYPES, generate


def _oracle_script(sc):
    return [
        [{"type": "tool_use", "id": "a", "name": "list_services", "input": {}}],
        [{"type": "tool_use", "id": "b", "name": "search_logs", "input": {"service": sc.root_service, "level": "ERROR"}},
         {"type": "tool_use", "id": "c", "name": "get_recent_deploys", "input": {}}],
        [{"type": "tool_use", "id": "d", "name": "submit_diagnosis", "input": {
            "status": "diagnosed", "root_cause_service": sc.root_service, "fault_type": sc.fault_type,
            "evidence": [{"observation_id": "obs-1", "quote": "Time now:"}],
            "action": sorted(ACTIONS[sc.fault_type])[0], "target": sc.root_service, "remediation": "recommend action"}}],
    ]


def test_sim_is_deterministic():
    a, b = generate(7, "memory_leak"), generate(7, "memory_leak")
    assert a.metrics == b.metrics and a.logs == b.logs and a.root_service == b.root_service


def test_every_fault_type_breaches_slo_at_gateway():
    for ft in FAULT_TYPES:
        for seed in range(5):
            g = generate(seed, ft).metrics["gateway"]
            assert g["p95_latency_ms"][-1] > 250 or g["error_rate"][-1] > 1.5, (ft, seed)


def test_graph_runs_through_mcp_and_grades():
    sc = generate(3, "config_error")
    out = asyncio.run(run_scenario(sc, ScriptedLLM(_oracle_script(sc))))
    assert out["grade"]["both_ok"] and out["tool_calls"] == 3 and out["steps"] == 3
    assert any(t["type"] == "tool_result" for t in out["trace"])


def test_step_budget_abstains_without_extra_call():
    sc = generate(4, "cert_expiry")
    loop = [[{"type": "tool_use", "id": "a", "name": "list_services", "input": {}}]]
    forced = ScriptedLLM(loop * 3 + [[{"type": "tool_use", "id": "z", "name": "submit_diagnosis", "input": {
        "root_cause_service": sc.root_service, "fault_type": sc.fault_type, "evidence": [], "remediation": "renew certificate"}}]])
    out = asyncio.run(run_scenario(sc, forced, max_steps=3))
    assert out["diagnosis"]["status"] == "insufficient_evidence"
    assert out["trace"][-1].get("budget_exhausted")
    assert out["model_calls"] == 3 and forced.calls == 3


def test_no_rag_hides_runbook_tool():
    sc = generate(1, "bad_deploy")
    s = [[{"type": "tool_use", "id": "a", "name": "search_runbooks", "input": {"query": "x"}}],
         [{"type": "tool_use", "id": "b", "name": "submit_diagnosis", "input": {
             "root_cause_service": "gateway", "fault_type": "bad_deploy", "evidence": [], "remediation": ""}}]]
    out = asyncio.run(run_scenario(sc, ScriptedLLM(s), use_rag=False))
    assert any(t["type"] == "tool_result" and t["output"].startswith("ERROR") for t in out["trace"])


def test_retrieval_finds_cert_runbook():
    top = get_index().search("x509 certificate has expired handshake failed", 1)[0][0]
    assert top.runbook == "tls-certificate-expiry"


def test_baseline_is_weak_but_gradable():
    wins = sum(grade(sc, baseline_latest_deploy(sc))["both_ok"] for sc in (generate(i, FAULT_TYPES[i % 6]) for i in range(60)))
    assert 0 <= wins < 30


def test_web_app_roundtrip(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as m

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    import tempfile
    monkeypatch.setenv("BUDGET_DB", tempfile.mktemp(suffix=".sqlite3"))

    def fake_llm(model):
        return ScriptedLLM([
            [{"type": "tool_use", "id": "a", "name": "list_services", "input": {}}],
            [{"type": "tool_use", "id": "d", "name": "submit_diagnosis", "input": {
                "status": "diagnosed", "root_cause_service": "gateway", "fault_type": "traffic_spike",
                "evidence": [{"observation_id": "obs-1", "quote": "Time now:"}],
                "action": "scale", "target": "gateway", "remediation": "Recommend scaling after approval"}}]
        ], model=model)

    monkeypatch.setattr(m, "make_llm", fake_llm)
    c = TestClient(m.app)
    assert c.get("/").status_code == 200
    r = c.post("/api/investigate", json={"fault_type": "traffic_spike"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ground_truth"]["fault_type"] == "traffic_spike" and body["tool_calls"] == 1
    assert c.post("/api/investigate", json={"model": "gpt-x"}).status_code == 400


def test_failure_preserves_usage_and_trace():
    class FailsAfterOneCall(ScriptedLLM):
        async def complete(self, *args, **kwargs):
            if self.calls:
                raise RuntimeError("injected failure")
            return await super().complete(*args, **kwargs)
    sc = generate(1, "bad_deploy")
    llm = FailsAfterOneCall([[{"type": "tool_use", "id": "a", "name": "list_services", "input": {}}]], model="claude-haiku-4-5-20251001")
    out = asyncio.run(run_scenario(sc, llm))
    assert out["error"] and out["usage"]["input_tokens"] == 1000
    assert out["usage"]["output_tokens"] == 100 and out["cost_usd"] > 0
    assert out["model_calls"] == 2 and out["steps"] == 1
    assert out["latency_s"] > 0 and out["tool_calls"] == 1
    assert any(t["type"] == "tool_result" for t in out["trace"])


def test_forged_evidence_is_rejected_through_graph():
    sc = generate(2, "bad_deploy")
    script = _oracle_script(sc)
    script[-1][0]["input"]["evidence"] = [{"observation_id": "obs-999", "quote": "invented"}]
    out = asyncio.run(run_scenario(sc, ScriptedLLM(script), max_steps=3))
    assert out["diagnosis"]["status"] == "insufficient_evidence"
    assert any(t["type"] == "validation_error" for t in out["trace"])


def test_web_cancel_settles_full_reservation(monkeypatch, tmp_path):
    import app.main as m
    monkeypatch.setenv("BUDGET_DB", str(tmp_path/"ledger.sqlite3"))
    rid = m.ledger().reserve(.5, 2, "visitor")
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError()
    monkeypatch.setattr(m, "run_scenario", cancelled)
    monkeypatch.setattr(m, "make_llm", lambda model: ScriptedLLM([[]], model=model))
    try:
        asyncio.run(m.execute(rid, m.InvestigateRequest()))
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Cancellation must propagate")
    assert m.ledger().spent() == .5


def test_background_run_persists_replay(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as m
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("BUDGET_DB", str(tmp_path/"ledger.sqlite3"))
    monkeypatch.setattr(m, "make_llm", lambda model: ScriptedLLM([[{"type": "tool_use", "id": "d", "name": "submit_diagnosis", "input": insufficient()}]], model=model))
    with TestClient(m.app) as client:
        response = client.post("/api/runs", json={"fault_type": "traffic_spike"})
        assert response.status_code == 202
        rid = response.json()["run_id"]
        import time
        for _ in range(100):
            status = client.get(f"/api/runs/{rid}").json()
            if status["status"] == "completed":
                break
            time.sleep(.01)
        assert status["status"] == "completed"
        assert status["result"]["run_id"] == rid
        assert m.ledger().replay(rid)


def test_rule_baseline_agrees_over_mcp_transport():
    from copilot.baselines import baseline_rules, baseline_rules_mcp
    from evals.cases import scenarios
    async def check():
        for sc in scenarios(6, 0) + scenarios(24, 0, "correlated-v1"):
            direct, _, direct_calls = baseline_rules(sc)
            transported, _, mcp_calls = await baseline_rules_mcp(sc)
            assert direct == transported
            assert direct_calls == mcp_calls
    asyncio.run(check())
