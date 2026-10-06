"""Validated diagnoses cite exact excerpts from successful MCP observations.

Reference validation establishes provenance, not that an inference is correct.
"""
from .sim import FAULT_TYPES, SERVICES

ACTIONS = {
    "bad_deploy": {"rollback"}, "memory_leak": {"restart", "rollback"},
    "slow_dependency": {"optimize_query", "scale"}, "config_error": {"restore_config"},
    "cert_expiry": {"renew_certificate"}, "traffic_spike": {"scale", "rate_limit"},
}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["diagnosed", "insufficient_evidence"]},
        "root_cause_service": {"type": ["string", "null"], "enum": SERVICES + [None]},
        "fault_type": {"type": ["string", "null"], "enum": FAULT_TYPES + [None]},
        "evidence": {"type": "array", "maxItems": 5, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"observation_id": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["observation_id", "quote"]}},
        "action": {"type": ["string", "null"], "enum": sorted(set().union(*ACTIONS.values())) + [None]},
        "target": {"type": ["string", "null"], "enum": SERVICES + [None]},
        "remediation": {"type": "string", "maxLength": 2000},
    },
    "required": ["status", "root_cause_service", "fault_type", "evidence", "action", "target", "remediation"],
}


def insufficient(reason="Investigation budget exhausted."):
    return dict(status="insufficient_evidence", root_cause_service=None, fault_type=None,
                evidence=[], action=None, target=None, remediation=reason)


def validate_diagnosis(d, observations):
    if not isinstance(d, dict) or set(d) != set(SCHEMA["required"]):
        raise ValueError("Diagnosis must contain exactly the required fields")
    if d["status"] not in ("diagnosed", "insufficient_evidence"):
        raise ValueError("Invalid status")
    if not isinstance(d["remediation"], str) or len(d["remediation"]) > 2000:
        raise ValueError("Invalid remediation")
    evidence = d["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 5:
        raise ValueError("Evidence must be an array of at most five references")
    for ref in evidence:
        if not isinstance(ref, dict) or set(ref) != {"observation_id", "quote"}:
            raise ValueError("Evidence needs observation_id and quote")
        oid, quote = ref["observation_id"], ref["quote"]
        if not isinstance(oid, str) or not isinstance(quote, str) or not quote.strip():
            raise ValueError("Invalid evidence reference")
        if oid not in observations or quote not in observations[oid]:
            raise ValueError("Evidence must quote a successful retrieved observation exactly")
    if d["status"] == "insufficient_evidence":
        if any(d[k] is not None for k in ("root_cause_service", "fault_type", "action", "target")):
            raise ValueError("Insufficient evidence must not specify a diagnosis or action")
    else:
        if d["root_cause_service"] not in SERVICES or d["fault_type"] not in FAULT_TYPES:
            raise ValueError("Unknown service or fault")
        if not evidence or not isinstance(d["action"], str) or d["action"] not in set().union(*ACTIONS.values()) or d["target"] not in SERVICES:
            raise ValueError("Diagnosis needs evidence and a structured action/target")
    return d
