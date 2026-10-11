"""Validated diagnoses cite exact excerpts from successful MCP observations.

Reference validation establishes provenance, not that an inference is correct.
"""
import json

from .sim import FAULT_TYPES, SERVICES

PROMPT_VERSION = "evidence-v4-operational-checks"

ACTIONS = {
    "bad_deploy": {"rollback"}, "memory_leak": {"restart", "rollback"},
    "slow_dependency": {"optimize_query", "scale"}, "config_error": {"restore_config"},
    "cert_expiry": {"renew_certificate"}, "traffic_spike": {"scale", "rate_limit"},
}

# Conservative fallback policies, not version-specific recovery instructions.
# Never interpolate provider prose or infer a deployment version from telemetry.
RECOMMENDATIONS = {
    "rollback": "Consider rolling back {target} only after verifying the previous healthy release in deployment records and checking schema/configuration compatibility. A rollback version has not been verified by this investigation.",
    "restart": "Consider a controlled restart of {target} after checking redundancy, draining traffic where required, and confirming the service-specific restart procedure. A restart may only provide temporary relief.",
    "optimize_query": "Investigate slow queries affecting {target} using query plans and the service runbook before making a query or index change. No specific query change has been verified.",
    "scale": "Consider scaling {target} after checking capacity limits and downstream bottlenecks. Verify the permitted replica or resource limits in the service runbook before changing capacity.",
    "restore_config": "Compare {target}'s active configuration with a verified healthy configuration. Confirm compatibility and the service rollback procedure before restoring it; no specific configuration revision has been verified.",
    "renew_certificate": "Verify {target}'s certificate, issuer, expiry and trust-chain requirements. Follow the service certificate-rotation procedure, including any required overlap of trust bundles, before replacing it.",
    "rate_limit": "Consider rate limiting or load shedding for {target} after verifying the service policy, protected traffic classes and permitted thresholds. No specific limit has been verified.",
}


def recommend(action, target):
    return ("Recommendation only; no change has been executed. "
            + RECOMMENDATIONS[action].format(target=target)
            + " After any approved change, check service and caller error rates and latency against their configured SLOs.")


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
        "remediation": {"type": "string", "maxLength": 2000,
                        "description": "Brief recommendation only. Do not invent release versions, implementation mechanisms or numeric thresholds. The server replaces this prose with a conservative action-specific recommendation."},
    },
    "required": ["status", "root_cause_service", "fault_type", "evidence", "action", "target", "remediation"],
}


def insufficient(reason="Investigation budget exhausted."):
    return dict(status="insufficient_evidence", root_cause_service=None, fault_type=None,
                evidence=[], action=None, target=None, remediation=reason)


def _require_check(d, observations, observation_tools, tool, kind, expected):
    assessments = []
    for oid, text in observations.items():
        if observation_tools.get(oid) != tool:
            continue
        try:
            assessment = json.loads(text)
        except (ValueError, TypeError):
            continue
        if (isinstance(assessment, dict) and assessment.get("kind") == kind
                and assessment.get("service") == d["target"]):
            assessments.append((oid, assessment.get("status")))
    cited = {ref["observation_id"] for ref in d["evidence"]}
    if not assessments or any(status != expected for _, status in assessments) or not any(oid in cited for oid, _ in assessments):
        statuses = ", ".join(sorted({str(status) for _, status in assessments})) or "missing"
        detail = ("The log-emitting caller is not necessarily the certificate owner; normal peer metrics do not establish certificate health. If ownership/expiry is unknown or conflicting, use insufficient_evidence."
                  if kind == "certificate" else "Scaling is not verified at a replica limit or with unknown headroom. Do not infer permission to raise limits; consider another compatible action with service-policy verification, or insufficient_evidence.")
        raise ValueError(f"Call {tool}(service={d['target']!r}) and cite its {expected} assessment. Current assessment: {statuses}. {detail}")


def validate_diagnosis(d, observations, observation_tools=None):
    if not isinstance(d, dict):
        raise ValueError("Diagnosis must be an object")
    if set(d) != set(SCHEMA["required"]):
        missing = ", ".join(sorted(set(SCHEMA["required"])-set(d))) or "none"
        extra = ", ".join(sorted(set(d)-set(SCHEMA["required"]))) or "none"
        raise ValueError(f"Diagnosis fields invalid; missing: {missing}; unexpected: {extra}")
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
        if oid not in observations:
            available = ", ".join(observations) or "none"
            raise ValueError(f"Unknown observation_id {oid!r}. Successful observation IDs: {available}. Cite only a successful observation.")
        if quote not in observations[oid]:
            raise ValueError(f"Quote for {oid} is not an exact substring of that observation. Copy a contiguous excerpt verbatim, including timestamps, punctuation and spacing; do not paraphrase, add ellipses or combine lines.")
    if d["status"] == "insufficient_evidence":
        if any(d[k] is not None for k in ("root_cause_service", "fault_type", "action", "target")):
            raise ValueError("Insufficient evidence must not specify a diagnosis or action")
        return {**d, "remediation": "Insufficient evidence to recommend a recovery action. Gather missing telemetry and consult the service owner before selecting a change."}
    else:
        if d["root_cause_service"] not in SERVICES or d["fault_type"] not in FAULT_TYPES:
            raise ValueError("Unknown service or fault")
        if not evidence or not isinstance(d["action"], str) or d["action"] not in set().union(*ACTIONS.values()) or d["target"] not in SERVICES:
            raise ValueError("Diagnosis needs evidence and a structured action/target")
        if d["action"] not in ACTIONS[d["fault_type"]]:
            raise ValueError(f"Action is incompatible with {d['fault_type']}; allowed: {', '.join(sorted(ACTIONS[d['fault_type']]))}")
        if d["target"] != d["root_cause_service"]:
            raise ValueError("Action target must match the diagnosed root-cause service")
        if d["fault_type"] == "cert_expiry":
            _require_check(d, observations, observation_tools or {}, "check_certificate", "certificate", "expiry_supported")
        if d["action"] == "scale":
            _require_check(d, observations, observation_tools or {}, "check_capacity", "capacity", "headroom")
        return {**d, "remediation": recommend(d["action"], d["target"])}
    return d
