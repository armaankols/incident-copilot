"""Affirmative change evidence and missing-data regressions; no provider calls."""
import asyncio
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from copilot.checks import change_check
from copilot.diagnosis import SCHEMA, insufficient, validate_diagnosis
from copilot.llm import ScriptedLLM
from copilot.mcp_server import build_server
from copilot.runner import run_scenario
from copilot.sim import SERVICES, generate
from evals.cases import scenarios


def candidate(service, fault, quote='"status": "supported"'):
    return dict(status="diagnosed", root_cause_service=service, fault_type=fault,
                evidence=[dict(observation_id="obs-1", quote=quote)], action=None,
                target=None, remediation="Investigate")


@pytest.mark.parametrize("fault,offset", [("bad_deploy", 0), ("config_error", 3)])
def test_latest_release_supports_local_fault_and_paraphrases(fault, offset):
    for suite in ("original", "correlated-v2"):
        sc = scenarios(1, 0, suite, offset=offset)[0]
        check = change_check(sc.logs, sc.deploys, sc.now, sc.root_service, fault)
        assert check["status"] == "supported"
        assert check["evidence"] and check["release"]["service"] == sc.root_service
        observations = {"obs-1": json.dumps(check)}
        assert validate_diagnosis(candidate(sc.root_service, fault), observations,
                                 {"obs-1": "check_change"})["status"] == "diagnosed"
        for other in SERVICES:
            if other != sc.root_service:
                assert change_check(sc.logs, sc.deploys, sc.now, other, fault)["status"] == "unknown"
        # No dependence on hidden grading labels.
        sc.root_service, sc.fault_type = "gateway", "traffic_spike"
        assert change_check(sc.logs, sc.deploys, sc.now, check["service"], fault) == check


@pytest.mark.parametrize("mutation", ["stale", "single", "different_build", "latest_release", "ambiguous_release", "caller", "missing_history", "coverage"])
def test_bad_deploy_requires_current_repeated_matching_build(mutation):
    sc = generate(0, "bad_deploy")
    service = sc.root_service
    kwargs = {}
    if mutation == "stale":
        sc.now += 10
    elif mutation == "single":
        sc.logs = [r for r in sc.logs if "unhandled exception" not in r[3] or r[0] == 118]
    elif mutation == "different_build":
        sc.logs = [(m, s, level, msg.replace("(build ", "(build wrong-")) for m, s, level, msg in sc.logs]
    elif mutation == "latest_release":
        sc.deploys.append(dict(service=service, minute=sc.now, version="v99", summary="new", author="test"))
    elif mutation == "ambiguous_release":
        release = next(d for d in sc.deploys if d["service"] == service)
        sc.deploys.append({**release, "version": "different"})
    elif mutation == "caller":
        sc.logs = [(m, "gateway" if s == service else s, level, msg) for m, s, level, msg in sc.logs]
    elif mutation == "missing_history":
        sc.deploys = []
    else:
        kwargs["available"] = False
    assert change_check(sc.logs, sc.deploys, sc.now, service, "bad_deploy", **kwargs)["status"] == "unknown"


@pytest.mark.parametrize("mutation", ["no_config", "different_pool", "different_timeout", "generic_errors", "recovered", "unrecognized_new_config"])
def test_config_error_requires_matching_active_settings_and_local_failure(mutation):
    sc = generate(3, "config_error")
    if mutation == "no_config":
        sc.logs = [r for r in sc.logs if "loaded config:" not in r[3]]
    elif mutation == "different_pool":
        sc.logs = [(m, s, level, msg.replace("db.pool.max=5", "db.pool.max=50")) for m, s, level, msg in sc.logs]
    elif mutation == "different_timeout":
        sc.logs = [(m, s, level, msg.replace("db.pool.timeout=3000ms", "db.pool.timeout=9000ms")) for m, s, level, msg in sc.logs]
    elif mutation == "generic_errors":
        sc.logs = [(m, s, level, "upstream requests failing" if "connection pool exhausted" in msg else msg) for m, s, level, msg in sc.logs]
    elif mutation == "recovered":
        sc.logs = [r for r in sc.logs if r[0] < 90]
    else:
        sc.logs.append((sc.now, sc.root_service, "INFO", "loaded config: new settings unavailable"))
    assert change_check(sc.logs, sc.deploys, sc.now, sc.root_service, "config_error")["status"] == "unknown"


@pytest.mark.parametrize("fault", ["bad_deploy", "config_error"])
def test_change_gate_requires_authentic_cited_service_and_fault_even_without_action(fault):
    good = dict(kind="change", service="orders", fault_type=fault, status="supported")
    d = candidate("orders", fault)
    for update, tool, cited in [({}, "search_logs", True), ({"service": "auth"}, "check_change", True),
                                ({"fault_type": "memory_leak"}, "check_change", True),
                                ({"status": "unknown"}, "check_change", True), ({}, "check_change", False)]:
        text = json.dumps({**good, **update})
        bad = {**d, "evidence": [dict(observation_id="obs-1", quote='"kind": "change"')]} if cited else {**d, "evidence": [dict(observation_id="obs-2", quote="symptom")]}
        with pytest.raises(ValueError, match="check_change"):
            validate_diagnosis(bad, {"obs-1": text, "obs-2": "symptom"}, {"obs-1": tool})
    with pytest.raises(ValueError, match="unknown"):
        validate_diagnosis(d, {"obs-1": json.dumps(good), "obs-2": json.dumps({**good, "status": "unknown"})},
                           {"obs-1": "check_change", "obs-2": "check_change"})


@pytest.mark.parametrize("filename", ["live-v5-traffic_spike-2026-10-12-2fa0a38e57f9.json", "live-v5-missing_evidence-2026-10-12-a09d83c85244.json"])
def test_recorded_unsupported_diagnosis_is_rejected_with_real_quotes(filename):
    record = json.loads((Path(__file__).resolve().parents[1]/"results"/filename).read_text())["records"][0]
    d = {k: record["diagnosis"][k] for k in SCHEMA["required"]}
    observations = {r["observation_id"]: r["quote"] for r in d["evidence"]}
    sc = generate(5, "traffic_spike") if "traffic" in filename else scenarios(1, 0, "correlated-v2", offset=18)[0]
    check = change_check(sc.logs, sc.deploys, sc.now, d["root_cause_service"], d["fault_type"],
                         available=sc.availability("deploys") == "available")
    assert check["status"] == "unknown"
    observations["obs-check"] = json.dumps(check)
    # Preserve genuine source excerpts while fitting the new compact interface.
    d["evidence"] = [{**ref, "quote": ref["quote"][:240]} for ref in d["evidence"][:3]]
    for action in (True, False):
        proposed = d if action else {**d, "action": None, "target": None}
        with pytest.raises(ValueError, match="check_change.*unknown"):
            validate_diagnosis(proposed, observations, {"obs-check": "check_change"})


def test_real_mcp_reports_unavailable_separately_from_known_empty():
    async def collect(sc):
        async with create_connected_server_and_client_session(build_server(sc, use_rag=False)) as session:
            output = {}
            for name, args in [("list_services", {}), ("query_metrics", dict(service="auth", metric="error_rate")),
                               ("query_metrics", dict(service="gateway", metric="error_rate")),
                               ("search_logs", {}), ("search_logs", dict(service="auth")),
                               ("get_recent_deploys", {}), ("check_certificate", dict(service="payments")),
                               ("check_capacity", dict(service="search")), ("check_change", dict(service="gateway", fault_type="config_error"))]:
                response = await session.call_tool(name, args)
                assert not response.isError
                output[(name, args.get("service"))] = "\n".join(c.text for c in response.content if hasattr(c, "text"))
            return output
    sc = scenarios(1, 0, "correlated-v2", offset=18)[0]
    assert set(sc.metrics) == {"gateway"}
    output = asyncio.run(collect(sc))
    assert "health unknown" in output[("list_services", None)]
    assert "UNAVAILABLE" in output[("query_metrics", "auth")]
    assert "latest=" in output[("query_metrics", "gateway")]
    assert "dependency telemetry unavailable" in output[("search_logs", None)]
    assert "UNAVAILABLE/PARTIAL" in output[("search_logs", "auth")]
    assert "UNAVAILABLE" in output[("get_recent_deploys", None)]
    for tool, service in [("check_certificate", "payments"), ("check_capacity", "search"), ("check_change", "gateway")]:
        assert json.loads(output[(tool, service)])["status"] == "unknown"
    known = generate(0, "bad_deploy")
    known.logs, known.deploys = [], []
    normal = asyncio.run(collect(known))
    assert normal[("search_logs", "auth")] == "No log lines matched in available records."
    assert normal[("get_recent_deploys", None)] == "No deploys in that window."
    # v1's historical numeric snapshot remains reproducible.
    assert len(scenarios(1, 0, "correlated-v1", offset=18)[0].metrics) == len(SERVICES)


def test_graph_rejects_missing_evidence_guess_then_accepts_model_abstention():
    sc = scenarios(1, 0, "correlated-v2", offset=18)[0]
    guessed = candidate("gateway", "config_error", '"status": "unknown"')
    script = [[dict(type="tool_use", id="check", name="check_change", input=dict(service="gateway", fault_type="config_error"))],
              [dict(type="tool_use", id="guess", name="submit_diagnosis", input=guessed)],
              [dict(type="tool_use", id="stop", name="submit_diagnosis", input=insufficient())]]
    result = asyncio.run(run_scenario(sc, ScriptedLLM(script), max_steps=3))
    assert result["error"] is None and result["diagnosis"]["status"] == "insufficient_evidence"
    assert result["termination_reason"] == "model_submission" and result["validation_rejections"] == 1
    assert result["model_calls"] == 3 and result["tool_calls"] == 1


def test_graph_rejects_decoy_release_and_retains_traffic_diagnosis_with_blocked_recovery():
    sc = generate(5, "traffic_spike")
    wrong = candidate("inventory", "bad_deploy", '"status": "unknown"')
    right = dict(status="diagnosed", root_cause_service="search", fault_type="traffic_spike",
                 evidence=[dict(observation_id="obs-2", quote='"status": "supported"'),
                           dict(observation_id="obs-3", quote='"status": "blocked"')],
                 action="scale", target="search", remediation="Scale")
    script = [[dict(type="tool_use", id="change", name="check_change", input=dict(service="inventory", fault_type="bad_deploy")),
               dict(type="tool_use", id="traffic", name="check_fault", input=dict(service="search", fault_type="traffic_spike")),
               dict(type="tool_use", id="capacity", name="check_capacity", input=dict(service="search"))],
              [dict(type="tool_use", id="wrong", name="submit_diagnosis", input=wrong)],
              [dict(type="tool_use", id="right", name="submit_diagnosis", input=right)]]
    result = asyncio.run(run_scenario(sc, ScriptedLLM(script), max_steps=3))
    assert result["error"] is None and result["grade"]["both_ok"]
    assert result["validation_rejections"] == 1 and result["termination_reason"] == "model_submission"
    assert result["diagnosis"]["action"] is None and result["diagnosis"]["recovery_status"] == "blocked"
