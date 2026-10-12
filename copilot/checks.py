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


def fault_check(logs, metrics, now, service, fault_type, *, available=True):
    """Corroborate the remaining synthetic patterns with local metrics and logs.

    Fixed thresholds/window sizes describe this simulator, not production SLOs or
    causal proof. Missing, malformed, stale or uncorroborated data stays unknown.
    """
    import math
    from statistics import median
    from .sim import callers_of

    if service not in SERVICES or fault_type not in ("memory_leak", "slow_dependency", "traffic_spike"):
        raise ValueError("Expected a known service and memory_leak, slow_dependency or traffic_spike")
    result = dict(kind="fault", service=service, fault_type=fault_type, checked_at=ts(now),
                  status="unknown", coverage="available" if available else "unavailable",
                  source="simulated local metrics and fault records; no causal experiment",
                  reason="Required local fault evidence and metric corroboration are missing.", evidence=[])
    if not available:
        return result
    keys = {"memory_leak": ("memory_mb", "restarts"), "slow_dependency": ("p95_latency_ms",),
            "traffic_spike": ("rps", "cpu_pct", "error_rate", "p95_latency_ms")}[fault_type]
    try:
        series = {k: [float(v) for v in metrics[service][k][:now+1]] for k in keys}
        if now < 59 or any(len(v) != now+1 or any(not math.isfinite(x) or x < 0 for x in v) for v in series.values()):
            return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return result
    baseline_start = max(0, now-119)
    stats = {k: dict(baseline=round(median(v[baseline_start:baseline_start+30]), 2),
                     recent=round(median(v[now-4:now+1]), 2)) for k, v in series.items()}
    rows = [r for r in logs if now-120 < r[0] <= now]
    local = [r for r in rows if r[1] == service]
    recent = [r for r in local if now-10 < r[0] <= now and r[2] in ("WARN", "ERROR")]
    evidence = []
    if fault_type == "slow_dependency":
        pattern = re.compile(r"^(?:(?:slow query|database statement exceeded deadline) \(\d+ms\):|(?:thread pool saturated|worker executor has no free slots), queue depth \d+; request exceeded \d+ms budget$)")
        failures = [r for r in recent if pattern.search(r[3])]
        peers = [r for r in rows if now-5 < r[0] <= now and r[1] in callers_of(service) and r[2] == "ERROR"
                 and re.fullmatch(rf"timeout after \d+ms calling {re.escape(service)}", r[3])]
        latency = stats["p95_latency_ms"]
        supported = (len({r[0] for r in failures}) >= 2 and any(r[0] > now-5 for r in failures)
                     and bool(peers) and latency["recent"] >= max(latency["baseline"]*3, latency["baseline"]+250))
        evidence = failures[-2:] + peers[-1:]
    elif fault_type == "traffic_spike":
        pattern = re.compile(r"^(?:rate limiter shedding load|admission controller rejecting excess requests): 429 returned for \d+% of requests$")
        failures = [r for r in recent if pattern.search(r[3])]
        rps, latency, errors = stats["rps"], stats["p95_latency_ms"], stats["error_rate"]
        supported = (len({r[0] for r in failures}) >= 2 and any(r[0] > now-5 for r in failures)
                     and rps["baseline"] > 0 and rps["recent"] >= 3*rps["baseline"]
                     and stats["cpu_pct"]["recent"] >= 70 and errors["recent"] >= errors["baseline"]+1
                     and latency["recent"] >= 2*latency["baseline"])
        evidence = failures[-2:]
    else:
        ooms = [r for r in local if r[2] == "ERROR" and re.fullmatch(
            r"container terminated: (?:OOMKilled|memory cgroup limit exceeded) \(exit code 137\)", r[3])]
        pressure = [r for r in recent if re.fullmatch(r"GC pause \d+ms, heap (?:[7-9]\d|100)% of \d+MB", r[3])]
        memory, restarts = series["memory_mb"], series["restarts"]
        def growing(end):
            start = end-20
            return (start >= baseline_start and memory[end]-memory[start] >= 150
                    and sum(memory[i] > memory[i-1] for i in range(start+1, end+1)) >= 16)
        ooms = [r for r in ooms if baseline_start+21 <= r[0] <= now-21
                and restarts[r[0]] > restarts[r[0]-1] and growing(r[0]-1)]
        # Recent pressure can remain high after regrowth reaches the memory cap.
        regrowing = any(growing(end) for end in range(max(baseline_start+20, now-10), now+1))
        supported = bool(ooms and pressure and regrowing
                         and stats["memory_mb"]["recent"] >= 1.5*stats["memory_mb"]["baseline"])
        evidence = ooms[-1:] + pressure[-2:]
    result["metric_summary"] = stats
    if supported:
        result.update(status="supported", reason="Service-local fault records are corroborated by observed metric changes.",
                      evidence=[_record(r) for r in evidence])
    return result
