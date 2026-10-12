"""Narrow, log-backed operational assessments for the synthetic demo.

These checks use telemetry only, never injected root/fault labels. They are not
live certificate probes or infrastructure permission/capacity checks.
"""
import re

from .sim import SERVICES, ts


def _record(row):
    minute, service, level, message = row
    return {"time": ts(minute), "service": service, "level": level, "message": message}


def certificate_check(logs, now, service):
    if service not in SERVICES:
        raise ValueError("Unknown service")
    rows = [r for r in logs if now-120 < r[0] <= now]
    pattern = re.compile(rf"tls: certificate for {re.escape(service)}\.internal expires in (\d+)m\b")
    notices = [(r, r[0]+int(m.group(1))) for r in rows if r[1] == service
               and (m := pattern.search(r[3]))]
    peers = [r for r in rows if now-5 < r[0] <= now and r[2] == "ERROR"
             and f"calling {service}: x509: certificate has expired" in r[3]]
    rotations = [r for r in rows if r[1] == service
                 and f"tls: certificate for {service}.internal renewed" in r[3]]
    status = "unknown"
    if notices and peers:
        latest = max(r[0] for r, expiry in notices)
        expiries = {expiry for r, expiry in notices if r[0] == latest}
        if len(expiries) != 1 or next(iter(expiries)) > now or any(r[0] >= latest for r in rotations):
            status = "conflicting"
        else:
            status = "expiry_supported"
    return {"kind": "certificate", "service": service, "checked_at": ts(now),
            "status": status, "source": "simulated logs; no live TLS probe",
            "evidence": [_record(r) for r, expiry in notices] + [_record(r) for r in peers[-3:]]
                        + [_record(r) for r in rotations[-3:]]}


def capacity_check(logs, now, service):
    if service not in SERVICES:
        raise ValueError("Unknown service")
    snapshots = []
    for row in logs:
        if row[1] != service or not now-5 < row[0] <= now:
            continue
        match = re.search(r"autoscaler (at max replicas|replicas) \((\d+)/(\d+)\)", row[3])
        if match:
            current, maximum = int(match[2]), int(match[3])
            status = ("unknown" if maximum < 1 or (match[1] == "at max replicas" and current < maximum)
                      else "blocked" if current >= maximum else "headroom")
            snapshots.append((row, status, current, maximum))
    latest = max((r[0] for r, *_ in snapshots), default=None)
    latest_rows = [x for x in snapshots if x[0][0] == latest]
    values = {(status, current, maximum) for row, status, current, maximum in latest_rows}
    status = "unknown" if not values else "conflicting" if len(values) > 1 else next(iter(values))[0]
    return {"kind": "capacity", "service": service, "checked_at": ts(now), "status": status,
            "source": "simulated autoscaler logs; no infrastructure permissions verified",
            "evidence": [_record(row) for row, *_ in latest_rows]}


def change_check(logs, deploys, now, service, fault_type, *, available=True):
    """Conservative template-specific support, not proof of causal intervention.

    Require the latest known release and localized affirmative failure records.
    A release on another service, old errors, or missing data cannot pass.
    """
    if service not in SERVICES or fault_type not in ("bad_deploy", "config_error"):
        raise ValueError("Expected a known service and bad_deploy or config_error")
    result = {"kind": "change", "service": service, "fault_type": fault_type,
              "checked_at": ts(now), "status": "unknown", "coverage": "available" if available else "unavailable",
              "source": "simulated release and local failure records; no causal experiment",
              "reason": "Required release-linked local fault evidence is missing or ambiguous.", "evidence": []}
    if not available:
        return result
    releases = [d for d in deploys if d["service"] == service and now-120 < d["minute"] <= now]
    if not releases:
        return result
    latest = max(d["minute"] for d in releases)
    releases = [d for d in releases if d["minute"] == latest]
    if len(releases) != 1:
        return result
    release = releases[0]
    version = re.escape(release["version"])
    local = [r for r in logs if r[1] == service and latest <= r[0] <= now]
    if fault_type == "bad_deploy":
        pattern = re.compile(rf"^(?:unhandled exception|request handler crashed) in .+ \(build {version}\)$")
        failures = [r for r in local if r[2] == "ERROR" and pattern.search(r[3])]
        corroboration = []
    else:
        config = re.compile(rf"^deployed {version}; loaded config: db\.pool\.max=(\d+) db\.pool\.timeout=(\d+)ms$")
        settings = [(r, int(m[1]), int(m[2])) for r in local if (m := config.search(r[3]))]
        if not settings:
            return result
        newest = max(r[0] for r, *_ in settings)
        if any(r[0] >= newest and "loaded config:" in r[3] and not config.search(r[3]) for r in local):
            return result
        settings = [x for x in settings if x[0][0] == newest]
        if len({(maximum, timeout) for r, maximum, timeout in settings}) != 1:
            return result
        row, maximum, timeout = settings[-1]
        if maximum < 1 or timeout < 1:
            return result
        failure = re.compile(rf"^(?:connection pool exhausted|all database client slots occupied): timed out after {timeout}ms waiting for connection \(pool max={maximum}, active={maximum}, waiting=\d+\)$")
        failures = [r for r in local if r[0] >= newest and r[2] == "ERROR" and failure.search(r[3])]
        corroboration = [row]
    # Repeated failures spanning time, including a current error, prevent old
    # recovered errors or a single diagnostic drill from satisfying this gate.
    if len({r[0] for r in failures}) < 2 or not any(now-5 < r[0] <= now for r in failures):
        return result
    result.update(status="supported", reason="Latest known release has repeated, current, service-local fault evidence.",
                  release=release, evidence=[_record(r) for r in corroboration + [failures[0], failures[-1]]])
    return result
