"""Ground-truth scoring; action compatibility is not remediation quality."""
from __future__ import annotations
from .sim import Scenario
from .diagnosis import ACTIONS

def grade(sc: Scenario, diagnosis: dict | None) -> dict:
    d = diagnosis or {}
    service_ok = d.get("root_cause_service") == sc.root_service
    type_ok = d.get("fault_type") == sc.fault_type
    rem_ok = (d.get("status") == "diagnosed" and service_ok and type_ok
              and d.get("target") == sc.root_service and d.get("action") in ACTIONS.get(sc.fault_type, set()))
    abstain = d.get("status") == "insufficient_evidence"
    expected_abstain = sc.fault_type == "insufficient_evidence"
    return {"service_ok": service_ok and not expected_abstain, "type_ok": type_ok and not expected_abstain,
            "both_ok": abstain if expected_abstain else service_ok and type_ok and not abstain,
            "remediation_ok": rem_ok, "abstained": abstain}


def baseline_latest_deploy(sc: Scenario) -> dict:
    """Non-LLM baseline: blame the most recent deploy and call it a bad deploy."""
    if not sc.deploys:
        from .diagnosis import insufficient
        return insufficient("No deployment evidence available.")
    last = max(sc.deploys, key=lambda d: d["minute"])
    return {"root_cause_service": last["service"], "fault_type": "bad_deploy", "evidence": [], "remediation": "roll back"}
