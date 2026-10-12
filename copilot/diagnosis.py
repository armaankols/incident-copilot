"""Validated diagnoses cite exact excerpts from successful MCP observations.

Reference validation establishes provenance, not that an inference is correct.
"""
import json
import re

from .sim import FAULT_TYPES, SERVICES

PROMPT_VERSION = "evidence-v8-observation-id-submission"
MAX_EVIDENCE = 3
MAX_QUOTE_CHARS = 240

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
        "evidence": {"type": "array", "maxItems": MAX_EVIDENCE, "uniqueItems": True,
                     "description": "Select 1-3 successful observation IDs, including the required fault assessment. Example: [\"obs-12\", \"obs-13\"]. The server attaches exact excerpts; do not supply quotes or objects. Use [] for abstention.",
                     "items": {"type": "string", "minLength": 1, "maxLength": 64}},
        "action": {"type": ["string", "null"], "enum": sorted(set().union(*ACTIONS.values())) + [None],
                   "description": "Proposed recovery action, or null when no action is verified. A supported diagnosis does not require an action."},
        "target": {"type": ["string", "null"], "enum": SERVICES + [None],
                   "description": "Recovery target; null when action is null. Keep the diagnosed root_cause_service even when recovery is unavailable."},
    },
    "required": ["status", "root_cause_service", "fault_type", "evidence", "action", "target"],
}


def insufficient(reason="Investigation budget exhausted."):
    return dict(status="insufficient_evidence", root_cause_service=None, fault_type=None,
                evidence=[], action=None, target=None, remediation=reason)


class OperationalCheckError(ValueError):
    def __init__(self, message, statuses):
        super().__init__(message)
        self.recovery_status = "blocked" if "blocked" in statuses else "unverified"


def _require_check(d, observations, observation_tools, tool, kind, expected, fault_type=None):
    assessments = []
    for oid, text in observations.items():
        if observation_tools.get(oid) != tool:
            continue
        try:
            assessment = json.loads(text)
        except (ValueError, TypeError):
            continue
        if (isinstance(assessment, dict) and assessment.get("kind") == kind
                and assessment.get("service") == d["root_cause_service"]
                and (fault_type is None or assessment.get("fault_type") == fault_type)):
            assessments.append((oid, assessment.get("status")))
    cited = {ref["observation_id"] for ref in d["evidence"]}
    if not assessments or any(status != expected for _, status in assessments) or not any(oid in cited for oid, _ in assessments):
        values = {str(status) for _, status in assessments}
        statuses = ", ".join(sorted(values)) or "missing"
        detail = ("Require affirmative fault evidence local to this service, corroborated by metrics. Generic caller symptoms or unavailable dependency telemetry do not establish its fault. If unknown, use insufficient_evidence."
                  if kind == "fault" else "A nearby deploy, caller symptoms, or unavailable telemetry do not support this fault. Require release-linked local exceptions for bad_deploy, or a loaded configuration and matching local configuration failure for config_error. If unavailable, use insufficient_evidence."
                  if kind == "change" else "The log-emitting caller is not necessarily the certificate owner; normal peer metrics do not establish certificate health. If ownership/expiry is unknown or conflicting, use insufficient_evidence."
                  if kind == "certificate" else "Scaling is not verified at a replica limit or with unknown headroom. Do not infer permission to raise limits. Retain a supported diagnosis with action=null and target=null.")
        args = f"service={d['root_cause_service']!r}" + (f", fault_type={fault_type!r}" if fault_type else "")
        raise OperationalCheckError(f"Call {tool}({args}) and select its observation ID in evidence; it must have status {expected}. Current assessment: {statuses}. {detail}", values)


def _excerpt(text, tool, service):
    """Take a real substring; never reformat or paraphrase an observation."""
    if not isinstance(text, str) or not text.strip() or text.startswith("ERROR:"):
        raise ValueError("Observation has no successful, usable evidence excerpt")
    if tool in ("check_change", "check_fault", "check_certificate", "check_capacity"):
        try:
            assessment = json.loads(text)
        except (ValueError, TypeError):
            assessment = None
        if isinstance(assessment, dict) and isinstance(assessment.get("status"), str):
            # Match the actual JSON spelling/spacing, not a new serialization.
            value = re.escape(json.dumps(assessment["status"], ensure_ascii=False))
            match = re.search(r'"status"\s*:\s*'+value, text)
            if match:
                return match.group(0)[:MAX_QUOTE_CHARS]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if tool == "list_services" and service:
        line = next((line for line in lines if line.startswith(service+" |")), lines[0])
    elif tool == "search_logs" and not lines[0].startswith("UNAVAILABLE"):
        records = [line for line in lines if re.match(r"\d\d:\d\d:\d\d ", line)]
        line = records[-1] if records else lines[0]
    else:
        line = lines[0]
    return line[:MAX_QUOTE_CHARS]


def _resolve_evidence(evidence, observations, observation_tools, service):
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE:
        raise ValueError(f"Evidence must be an array of at most {MAX_EVIDENCE} observation IDs")
    id_mode = all(isinstance(ref, str) for ref in evidence)
    legacy_mode = all(isinstance(ref, dict) for ref in evidence)
    if not id_mode and not legacy_mode:
        raise ValueError("Evidence must contain observation IDs only; mixed reference formats are invalid")
    if id_mode and len(set(evidence)) != len(evidence):
        raise ValueError("Evidence observation IDs must be unique")
    resolved = []
    for ref in evidence:
        if id_mode:
            oid = ref
            if not oid or len(oid) > 64:
                raise ValueError("Invalid evidence observation ID")
        else:
            # Compatibility path: older clients' quote claims still need checking.
            if set(ref) != {"observation_id", "quote"}:
                raise ValueError("Legacy evidence needs observation_id and quote")
            oid, quote = ref["observation_id"], ref["quote"]
            if not isinstance(oid, str) or not isinstance(quote, str) or not quote.strip():
                raise ValueError("Invalid evidence reference")
            if len(quote) > MAX_QUOTE_CHARS:
                raise ValueError(f"Quote for {oid} exceeds {MAX_QUOTE_CHARS} characters. Submit observation IDs instead.")
        if oid not in observations:
            available = ", ".join(observations) or "none"
            raise ValueError(f"Unknown observation_id {oid!r}. Successful observation IDs: {available}. Select only a successful observation.")
        if not isinstance(observations[oid], str) or not observations[oid].strip() or observations[oid].startswith("ERROR:"):
            raise ValueError(f"Observation {oid!r} has no successful, usable evidence excerpt")
        if id_mode:
            quote = _excerpt(observations[oid], observation_tools.get(oid), service)
        elif quote not in observations[oid]:
            raise ValueError(f"Quote for {oid} is not an exact substring of that observation. Submit observation IDs so the server can attach exact excerpts; legacy quotes must be copied verbatim.")
        resolved.append({"observation_id": oid, "quote": quote})
    return resolved


def validate_diagnosis(d, observations, observation_tools=None):
    if not isinstance(d, dict):
        raise ValueError("Diagnosis must be an object")
    # Older offline clients can still send remediation, but it is never used.
    required = set(SCHEMA["required"])
    if not required <= set(d) or set(d) - required - {"remediation"}:
        missing = ", ".join(sorted(set(SCHEMA["required"])-set(d))) or "none"
        extra = ", ".join(sorted(set(d)-required-{"remediation"})) or "none"
        raise ValueError(f"Diagnosis fields invalid; missing: {missing}; unexpected: {extra}")
    if d["status"] not in ("diagnosed", "insufficient_evidence"):
        raise ValueError("Invalid status")
    if "remediation" in d and (not isinstance(d["remediation"], str) or len(d["remediation"]) > 2000):
        raise ValueError("Invalid remediation")
    # Validate model-controlled enums before service-specific excerpt selection.
    if d["status"] == "diagnosed":
        if (not isinstance(d["root_cause_service"], str) or d["root_cause_service"] not in SERVICES
                or not isinstance(d["fault_type"], str) or d["fault_type"] not in FAULT_TYPES):
            raise ValueError("Unknown service or fault")
    elif any(d[k] is not None for k in ("root_cause_service", "fault_type", "action", "target")):
        raise ValueError("Insufficient evidence must not specify a diagnosis or action")
    evidence = _resolve_evidence(d["evidence"], observations, observation_tools or {}, d["root_cause_service"])
    d = {**d, "evidence": evidence}
    if d["status"] == "insufficient_evidence":
        return {**d, "recovery_status": "unavailable", "recovery_reason": "Diagnostic evidence is insufficient.",
                "remediation": "Insufficient evidence to recommend a recovery action. Gather missing telemetry and consult the service owner before selecting a change."}
    else:
        if not evidence:
            raise ValueError("Diagnosis needs evidence")
        if d["fault_type"] in ("bad_deploy", "config_error"):
            _require_check(d, observations, observation_tools or {}, "check_change", "change", "supported", d["fault_type"])
        if d["fault_type"] in ("memory_leak", "slow_dependency", "traffic_spike"):
            _require_check(d, observations, observation_tools or {}, "check_fault", "fault", "supported", d["fault_type"])
        # Certificate ownership is diagnostic evidence, even when no action is proposed.
        if d["fault_type"] == "cert_expiry":
            _require_check(d, observations, observation_tools or {}, "check_certificate", "certificate", "expiry_supported")
        if (d["action"] is None) != (d["target"] is None):
            raise ValueError("Action and target must both be null or both specified")
        if d["action"] is None:
            return {**d, "recovery_status": "unverified", "recovery_reason": "No recovery action was verified.",
                    "remediation": "Diagnosis recorded. No recovery action has been verified. Consult the service owner and verify the service recovery policy before selecting a change. No change has been executed."}
        if not isinstance(d["action"], str) or d["action"] not in set().union(*ACTIONS.values()) or d["target"] not in SERVICES:
            raise ValueError("Invalid action/target")
        if d["action"] not in ACTIONS[d["fault_type"]]:
            raise ValueError(f"Action is incompatible with {d['fault_type']}; allowed: {', '.join(sorted(ACTIONS[d['fault_type']]))}")
        if d["target"] != d["root_cause_service"]:
            raise ValueError("Action target must match the diagnosed root-cause service")
        if d["action"] == "scale":
            try:
                _require_check(d, observations, observation_tools or {}, "check_capacity", "capacity", "headroom")
            except OperationalCheckError as e:
                return {**d, "action": None, "target": None, "recovery_status": e.recovery_status,
                        "recovery_reason": str(e),
                        "remediation": "Diagnosis recorded. Scaling has not been verified and is not recommended. Consult the service owner about capacity limits and compatible recovery options. No change has been executed."}
        return {**d, "recovery_status": "recommended", "recovery_reason": "Compatible recommendation; service policy still requires verification.",
                "remediation": recommend(d["action"], d["target"])}
    return d
