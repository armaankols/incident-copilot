"""Log-backed ownership and capacity gates, with real MCP graph corrections."""
import asyncio
import json
from pathlib import Path

import pytest

from copilot.checks import capacity_check, certificate_check
from copilot.diagnosis import insufficient, validate_diagnosis
from copilot.llm import ScriptedLLM
from copilot.runner import run_scenario
from copilot.sim import generate
from tests.evidence import add_fault


def diagnosis(service="payments", fault="cert_expiry", action="renew_certificate", oid="obs-1", quote='"status": "expiry_supported"'):
    return dict(status="diagnosed", root_cause_service=service, fault_type=fault,
                target=service, action=action, evidence=[dict(observation_id=oid, quote=quote)],
                remediation="Provider recommendation")


def test_certificate_assessment_distinguishes_log_caller_and_peer():
    sc = generate(4, "cert_expiry")
    owner = certificate_check(sc.logs, sc.now, "payments")
    caller = certificate_check(sc.logs, sc.now, "orders")
    assert owner["status"] == "expiry_supported"
    assert caller["status"] == "unknown"
    assert any(e["service"] == "payments" for e in owner["evidence"])
    assert any(e["service"] == "orders" for e in owner["evidence"])


@pytest.mark.parametrize("change", ["no_local", "stale_peer", "future_peer", "renewed", "future_expiry"])
def test_certificate_ownership_requires_consistent_current_corroboration(change):
    logs = [(80, "payments", "WARN", "tls: certificate for payments.internal expires in 5m"),
            (99, "orders", "ERROR", "TLS handshake failed calling payments: x509: certificate has expired")]
    if change == "no_local":
        logs = logs[1:]
    elif change == "stale_peer":
        logs[1] = (90, *logs[1][1:])
    elif change == "future_peer":
        logs[1] = (101, *logs[1][1:])
    elif change == "renewed":
        logs.append((98, "payments", "INFO", "tls: certificate for payments.internal renewed"))
    else:
        logs[0] = (99, "payments", "WARN", "tls: certificate for payments.internal expires in 5m")
    assert certificate_check(logs, 100, "payments")["status"] in ("unknown", "conflicting")


def test_capacity_uses_latest_service_snapshot_and_fails_closed():
    logs = [(98, "search", "INFO", "autoscaler replicas (4/12)"),
            (99, "search", "WARN", "autoscaler at max replicas (12/12), cannot add capacity"),
            (100, "auth", "INFO", "autoscaler replicas (2/12)")]
    assert capacity_check(logs, 100, "search")["status"] == "blocked"
    assert capacity_check(logs[:1], 100, "search")["status"] == "headroom"
    assert capacity_check(logs, 110, "search")["status"] == "unknown"
    assert capacity_check(logs, 97, "search")["status"] == "unknown"
    logs.append((99, "search", "INFO", "autoscaler replicas (4/12)"))
    assert capacity_check(logs, 100, "search")["status"] == "conflicting"


def test_check_text_from_runbook_cannot_forge_operational_assessment():
    assessment = json.dumps(dict(kind="certificate", service="payments", status="expiry_supported"))
    for sources in ({}, {"obs-1": "search_runbooks"}):
        with pytest.raises(ValueError, match="check_certificate"):
            validate_diagnosis(diagnosis(), {"obs-1": assessment}, sources)
    assert validate_diagnosis(diagnosis(), {"obs-1": assessment}, {"obs-1": "check_certificate"})["target"] == "payments"


def test_positive_check_must_be_for_target_and_cited_without_omitting_conflicts():
    good = json.dumps(dict(kind="capacity", service="search", status="headroom"))
    d = diagnosis("search", "traffic_spike", "scale", quote='"status": "headroom"')
    def validate(proposed, observations, tools):
        return validate_diagnosis(*add_fault(proposed, observations, tools))
    assert validate(d, {"obs-1": good}, {"obs-1": "check_capacity"})["action"] == "scale"
    wrong = json.dumps(dict(kind="capacity", service="auth", status="headroom"))
    invalid_target = validate(d, {"obs-1": wrong}, {"obs-1": "check_capacity"})
    assert invalid_target["action"] is None and invalid_target["recovery_status"] == "unverified"
    blocked = json.dumps(dict(kind="capacity", service="search", status="blocked"))
    conflict = validate(d, {"obs-1": good, "obs-2": blocked}, {"obs-1": "check_capacity", "obs-2": "check_capacity"})
    assert conflict["action"] is None and conflict["recovery_status"] == "blocked"
    uncited = {**d, "evidence": [dict(observation_id="obs-2", quote="search traffic") ]}
    result = validate(uncited, {"obs-1": good, "obs-2": "search traffic"}, {"obs-1": "check_capacity"})
    assert result["action"] is None and result["recovery_status"] == "unverified"


def test_missing_or_malformed_check_rejects_scale_but_allows_abstention():
    d = diagnosis("search", "traffic_spike", "scale", quote="search traffic")
    result = validate_diagnosis(*add_fault(d, {"obs-1": "search traffic", "obs-2": "not JSON"}, {"obs-2": "check_capacity"}))
    assert result["action"] is None and result["recovery_status"] == "unverified"
    assert validate_diagnosis(insufficient(), {})["action"] is None


def test_graph_rejects_caller_certificate_diagnosis_then_accepts_supported_peer():
    sc = generate(4, "cert_expiry")
    script = [
        [dict(type="tool_use", id="caller", name="check_certificate", input=dict(service="orders")),
         dict(type="tool_use", id="peer", name="check_certificate", input=dict(service="payments"))],
        [dict(type="tool_use", id="bad", name="submit_diagnosis",
              input=diagnosis("orders", quote='"status": "unknown"'))],
        [dict(type="tool_use", id="good", name="submit_diagnosis", input=diagnosis(oid="obs-2"))],
    ]
    result = asyncio.run(run_scenario(sc, ScriptedLLM(script), max_steps=3))
    assert result["error"] is None and result["grade"]["both_ok"]
    assert result["diagnosis"]["target"] == "payments"
    assert result["model_calls"] == 3 and result["tool_calls"] == 2
    assert any(e["type"] == "validation_error" and "certificate owner" in e["output"] for e in result["trace"])


def test_graph_removes_blocked_scaling_without_discarding_diagnosis_or_guessing_alternative():
    sc = generate(5, "traffic_spike")
    blocked = diagnosis("search", "traffic_spike", "scale", quote='"status": "blocked"')
    blocked["evidence"].append(dict(observation_id="obs-2", quote='"status": "supported"'))
    alternative = {**blocked, "action": "rate_limit"}
    script = [
        [dict(type="tool_use", id="capacity", name="check_capacity", input=dict(service="search")),
         dict(type="tool_use", id="fault", name="check_fault", input=dict(service="search", fault_type="traffic_spike"))],
        [dict(type="tool_use", id="bad", name="submit_diagnosis", input=blocked)],
        [dict(type="tool_use", id="good", name="submit_diagnosis", input=alternative)],
    ]
    result = asyncio.run(run_scenario(sc, ScriptedLLM(script), max_steps=3))
    assert result["error"] is None and result["grade"]["both_ok"]
    assert result["diagnosis"]["action"] is None and result["diagnosis"]["target"] is None
    assert result["diagnosis"]["recovery_status"] == "blocked"
    assert result["model_calls"] == 2 and result["termination_reason"] == "model_submission"
    assert not any(e["type"] == "validation_error" for e in result["trace"])


def test_unknown_ownership_exhausts_budget_into_abstention_without_extra_call():
    sc = generate(4, "cert_expiry")
    sc.logs = []
    script = [[dict(type="tool_use", id="check", name="check_certificate", input=dict(service="payments"))],
              [dict(type="tool_use", id="submit", name="submit_diagnosis", input=diagnosis(quote='"status": "unknown"'))]]
    result = asyncio.run(run_scenario(sc, ScriptedLLM(script), max_steps=2))
    assert result["diagnosis"]["status"] == "insufficient_evidence"
    assert result["model_calls"] == 2


@pytest.mark.parametrize("filename, tool, check, fault, expected", [
    ("live-cert_expiry-2026-10-11-2c5ec81643c4.json", "check_certificate", certificate_check, "cert_expiry", "unknown"),
    ("live-traffic_spike-2026-10-11-8c9a12acc1d5.json", "check_capacity", capacity_check, "traffic_spike", "blocked"),
])
def test_actual_saved_failure_payload_cannot_publish_bad_recovery(filename, tool, check, fault, expected):
    root = Path(__file__).resolve().parents[1]
    record = json.loads((root/"results"/filename).read_text())["records"][0]
    d = {**record["diagnosis"], "evidence": [{**ref, "quote": ref["quote"][:240]} for ref in record["diagnosis"]["evidence"][:2]]}
    # Public saved evidence provides exact quoted fragments; this is not a model rerun.
    observations = {ref["observation_id"]: ref["quote"] for ref in d["evidence"]}
    sc = generate(record["seed"], fault)
    assessment = check(sc.logs, sc.now, d["target"])
    assert assessment["status"] == expected
    observations["obs-check"] = json.dumps(assessment)
    if fault == "cert_expiry":
        with pytest.raises(ValueError, match=expected):
            validate_diagnosis(d, observations, {"obs-check": tool})
    else:
        result = validate_diagnosis(*add_fault(d, observations, {"obs-check": tool}))
        assert result["status"] == "diagnosed" and result["root_cause_service"] == "search"
        assert result["action"] is None and result["recovery_status"] == "blocked"
