"""Deterministic incident simulator.

Generates metrics, logs and deploy history for a small fake microservice system with exactly one
injected fault. Every scenario has known ground truth (root-cause service + fault type), which is
what makes the eval harness objective: no LLM judge is needed to score a diagnosis.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

SERVICES = ["gateway", "auth", "orders", "payments", "inventory", "search", "postgres"]
TOPOLOGY = {  # caller -> callees
    "gateway": ["auth", "orders", "search"],
    "orders": ["payments", "inventory", "postgres"],
    "payments": ["postgres"],
    "inventory": ["postgres"],
    "auth": [],
    "search": [],
    "postgres": [],
}
FAULT_TYPES = ["bad_deploy", "memory_leak", "slow_dependency", "config_error", "cert_expiry", "traffic_spike"]
METRICS = ["error_rate", "p95_latency_ms", "cpu_pct", "memory_mb", "restarts", "rps"]
MINUTES = 120          # one sample per minute
ONSET = 80             # fault becomes visible around this minute
BASE_TIME = datetime(2026, 10, 1, 12, 0, 0)
MEM_LIMIT = 1024

ROOT_CANDIDATES = {
    "bad_deploy": ["orders", "payments", "inventory", "auth", "search"],
    "memory_leak": ["orders", "payments", "inventory", "auth", "search"],
    "slow_dependency": ["postgres", "inventory", "payments"],
    "config_error": ["orders", "payments", "inventory"],
    "cert_expiry": ["payments", "auth", "inventory"],
    "traffic_spike": ["gateway", "search"],
}
REMEDIATION_KEYWORDS = {
    "bad_deploy": ["rollback", "roll back", "revert"],
    "memory_leak": ["restart", "heap", "leak", "roll back", "rollback", "revert"],
    "slow_dependency": ["index", "query", "lock", "scale", "connection", "kill"],
    "config_error": ["revert", "rollback", "roll back", "restore", "pool"],
    "cert_expiry": ["renew", "rotate", "certificate"],
    "traffic_spike": ["scale", "rate limit", "rate-limit", "throttle", "block"],
}
BENIGN_SUMMARIES = [
    "Bump dependency versions", "Update README and docs", "Refactor request validation",
    "Add feature flag for new checkout banner", "Tune logging verbosity", "Migrate metrics client",
    "Fix typo in error message", "Improve retry backoff jitter",
]
AUTHORS = ["priya", "marcus", "lena", "diego", "yuki", "sam", "nadia"]
PATHS = ["orders", "cart", "items", "profile", "quote", "status", "checkout"]

BASELINE = {  # (mean, noise)
    "error_rate": (0.25, 0.06), "p95_latency_ms": (120.0, 10.0), "cpu_pct": (35.0, 3.0),
    "memory_mb": (520.0, 10.0), "restarts": (0.0, 0.0), "rps": (200.0, 12.0),
}
OVERRIDES = {
    "postgres": {"p95_latency_ms": (15.0, 2.0), "cpu_pct": (40.0, 3.0), "memory_mb": (700.0, 8.0)},
    "auth": {"p95_latency_ms": (45.0, 5.0)},
    "gateway": {"rps": (600.0, 30.0), "p95_latency_ms": (160.0, 12.0)},
}


@dataclass
class Scenario:
    seed: int
    fault_type: str
    root_service: str
    metrics: dict
    logs: list            # (minute, service, level, message)
    deploys: list         # dicts
    alert: str
    now: int = MINUTES - 1


def ts(minute: int, sec: int = 0) -> str:
    return (BASE_TIME + timedelta(minutes=minute, seconds=sec)).strftime("%H:%M:%S")


def callers_of(service: str) -> list[str]:
    return [s for s, callees in TOPOLOGY.items() if service in callees]


def ancestors(service: str) -> dict[str, int]:
    seen: dict[str, int] = {}
    frontier = [(service, 0)]
    while frontier:
        s, d = frontier.pop(0)
        for c in callers_of(s):
            if c not in seen:
                seen[c] = d + 1
                frontier.append((c, d + 1))
    return seen


def _add(series, start, delta, end=None, ramp=0):
    for m in range(max(0, start), min(MINUTES, end or MINUTES)):
        f = min(1.0, (m - start + 1) / ramp) if ramp else 1.0
        series[m] += delta * f


def _scale(series, start, factor, ramp=0):
    for m in range(max(0, start), MINUTES):
        f = min(1.0, (m - start + 1) / ramp) if ramp else 1.0
        series[m] *= 1 + (factor - 1) * f


def _propagate(rng, root, metrics, lat, err, start, ramp=3):
    for anc, d in ancestors(root).items():
        f = 0.65 ** (d - 1) * rng.uniform(0.85, 1.15)
        _add(metrics[anc]["p95_latency_ms"], start, lat * f, ramp=ramp)
        _add(metrics[anc]["error_rate"], start, err * f, ramp=ramp)


def _baseline(rng):
    metrics = {}
    for s in SERVICES:
        metrics[s] = {}
        for m in METRICS:
            mean, noise = OVERRIDES.get(s, {}).get(m, BASELINE[m])
            mean *= rng.uniform(0.9, 1.1) if m != "restarts" else 1
            metrics[s][m] = [max(0.0, rng.gauss(mean, noise)) for _ in range(MINUTES)]
    return metrics


def _noise_logs(rng):
    logs = []
    for s in SERVICES:
        for _ in range(rng.randint(25, 35)):
            m = rng.randint(0, MINUTES - 1)
            r = rng.random()
            if r < 0.55:
                logs.append((m, s, "INFO", f"GET /v1/{rng.choice(PATHS)} 200 {rng.randint(8, 140)}ms"))
            elif r < 0.7:
                logs.append((m, s, "INFO", "healthcheck ok"))
            elif r < 0.8:
                logs.append((m, s, "INFO", f"cache hit ratio {rng.uniform(0.82, 0.97):.2f}"))
            elif r < 0.9:
                logs.append((m, s, "WARN", "retrying request attempt 1/3 succeeded"))
            elif r < 0.96:
                logs.append((m, s, "WARN", "deprecated header X-Legacy-Id used by client"))
            else:
                logs.append((m, s, "ERROR", f"rejected malformed request body (400) on /v1/{rng.choice(PATHS)}"))
    return logs


def _deploy(rng, svc, minute, summary):
    return {"minute": minute, "service": svc, "author": rng.choice(AUTHORS), "summary": summary,
            "version": f"v{rng.randint(1, 4)}.{rng.randint(0, 19)}.{rng.randint(0, 9)}"}


def _benign_deploys(rng, root):
    out = []
    for _ in range(rng.randint(2, 4)):
        svc = rng.choice(SERVICES)
        minute = rng.randint(5, MINUTES - 3)
        if svc == root and minute >= 35:
            svc = rng.choice([s for s in SERVICES if s != root])
        out.append(_deploy(rng, svc, minute, rng.choice(BENIGN_SUMMARIES)))
    return out


# ----------------------------------------------------------------------------- fault injectors
def _bad_deploy(rng, root, metrics, logs, deploys):
    d = _deploy(rng, root, ONSET - 2, rng.choice(BENIGN_SUMMARIES))
    deploys.append(d)
    _add(metrics[root]["error_rate"], ONSET, rng.uniform(15, 35), ramp=2)
    _add(metrics[root]["p95_latency_ms"], ONSET, 40, ramp=2)
    _propagate(rng, root, metrics, 150, rng.uniform(6, 14), ONSET, ramp=2)
    exc = rng.choice(["NullPointerException", "KeyError 'customer_tier'", "TypeError: 'NoneType' has no attribute 'id'",
                      "IndexError: list index out of range"])
    handler = rng.choice(["validate_request", "build_response", "load_profile", "price_lookup"])
    for m in range(ONSET, MINUTES, 2):
        logs.append((m, root, "ERROR", f"unhandled exception in {handler}: {exc} (build {d['version']})"))
    for c in callers_of(root):
        for m in range(ONSET, MINUTES, 3):
            logs.append((m, c, "ERROR", f"upstream {root} returned 500 for POST /v1/{rng.choice(PATHS)}"))
    logs.append((ONSET - 2, root, "INFO", f"deployed {d['version']}, 3/3 replicas healthy"))


def _memory_leak(rng, root, metrics, logs, deploys):
    start = ONSET - 30
    deploys.append(_deploy(rng, root, start, rng.choice(
        ["Add in-process cache for lookups", "Cache customer lookups in memory", "Memoize pricing rules"])))
    oom = ONSET + rng.randint(2, 8)
    base = metrics[root]["memory_mb"][0]
    rate = (MEM_LIMIT - 20 - base) / (oom - start)
    for m in range(start, MINUTES):
        since = m - (oom + 1) if m > oom else m - start
        mem = base + rate * since + (60 if m > oom else 0)
        metrics[root]["memory_mb"][m] = min(MEM_LIMIT - 5, mem)
        frac = (metrics[root]["memory_mb"][m] - base) / (MEM_LIMIT - base)
        metrics[root]["cpu_pct"][m] += 30 * max(0, frac)
        metrics[root]["p95_latency_ms"][m] += 500 * max(0, frac) ** 2
        metrics[root]["error_rate"][m] += 6 * max(0, frac) ** 2
        metrics[root]["restarts"][m] = 1 if m >= oom else 0
    _add(metrics[root]["error_rate"], oom, 18, end=oom + 3)
    _propagate(rng, root, metrics, 220, 4, ONSET, ramp=8)
    for m in range(ONSET - 6, oom, 3):
        logs.append((m, root, "WARN", f"GC pause {rng.randint(600, 1400)}ms, heap {rng.randint(88, 97)}% of {MEM_LIMIT}MB"))
    logs.append((oom, root, "ERROR", "container terminated: OOMKilled (exit code 137)"))
    logs.append((oom + 1, root, "INFO", "service starting, loading configuration"))
    for m in range(oom + 12, MINUTES, 4):
        logs.append((m, root, "WARN", f"GC pause {rng.randint(300, 900)}ms, heap {rng.randint(70, 90)}% of {MEM_LIMIT}MB"))
    for c in callers_of(root):
        for m in range(oom, oom + 4):
            logs.append((m, c, "WARN", f"upstream {root} connection reset"))


def _slow_dependency(rng, root, metrics, logs, deploys):
    _add(metrics[root]["p95_latency_ms"], ONSET, 900 if root == "postgres" else 1300, ramp=4)
    _add(metrics[root]["cpu_pct"], ONSET, 40, ramp=4)
    _propagate(rng, root, metrics, 900, rng.uniform(4, 9), ONSET, ramp=4)
    for m in range(ONSET + 1, MINUTES, 2):
        if root == "postgres":
            logs.append((m, root, "WARN", f"slow query ({rng.randint(900, 2400)}ms): SELECT ... FROM orders WHERE customer_id=$1 (seq scan)"))
            if m % 6 == 1:
                logs.append((m, root, "WARN", "lock wait on relation orders held by autovacuum"))
        else:
            logs.append((m, root, "WARN", f"thread pool saturated, queue depth {rng.randint(120, 260)}; request exceeded 500ms budget"))
    for c in callers_of(root):
        for m in range(ONSET + 1, MINUTES, 2):
            logs.append((m, c, "ERROR", f"timeout after 1000ms calling {root}"))


def _config_error(rng, root, metrics, logs, deploys):
    summary = rng.choice(["Tune connection pool settings", "Update DB pool size and timeouts",
                          "Config: reduce max connections per instance"])
    d = _deploy(rng, root, ONSET - 3, summary)
    deploys.append(d)
    _add(metrics[root]["error_rate"], ONSET, rng.uniform(20, 30), ramp=2)
    _add(metrics[root]["p95_latency_ms"], ONSET, 700, ramp=2)
    _add(metrics[root]["cpu_pct"], ONSET, -8, ramp=2)
    _propagate(rng, root, metrics, 500, rng.uniform(6, 12), ONSET, ramp=2)
    logs.append((ONSET - 3, root, "INFO", f"deployed {d['version']}; loaded config: db.pool.max=5 db.pool.timeout=3000ms"))
    for m in range(ONSET, MINUTES, 2):
        logs.append((m, root, "ERROR", f"connection pool exhausted: timed out after 3000ms waiting for connection (pool max=5, active=5, waiting={rng.randint(20, 60)})"))
    for c in callers_of(root):
        for m in range(ONSET, MINUTES, 3):
            logs.append((m, c, "ERROR", f"upstream {root} returned 503 for GET /v1/{rng.choice(PATHS)}"))


def _cert_expiry(rng, root, metrics, logs, deploys):
    _scale(metrics[root]["rps"], ONSET, 0.08)
    _add(metrics[root]["cpu_pct"], ONSET, -14, ramp=1)
    not_after = f"{BASE_TIME + timedelta(minutes=ONSET):%Y-%m-%dT%H:%M:%SZ}"
    for c in callers_of(root):
        _add(metrics[c]["error_rate"], ONSET, rng.uniform(25, 40), ramp=1)
        _add(metrics[c]["p95_latency_ms"], ONSET, 250, ramp=1)
        for m in range(ONSET, MINUTES, 2):
            logs.append((m, c, "ERROR", f"TLS handshake failed calling {root}: x509: certificate has expired (notAfter={not_after})"))
    _propagate(rng, root, metrics, 200, 5, ONSET, ramp=1)
    logs.append((ONSET - 25, root, "WARN", f"tls: certificate for {root}.internal expires in 25m (auto-renewal job disabled)"))
    logs.append((ONSET - 5, root, "WARN", f"tls: certificate for {root}.internal expires in 5m (auto-renewal job disabled)"))


def _traffic_spike(rng, root, metrics, logs, deploys):
    _scale(metrics[root]["rps"], ONSET, rng.uniform(4.5, 6.0), ramp=5)
    _add(metrics[root]["cpu_pct"], ONSET, 60, ramp=5)
    _add(metrics[root]["p95_latency_ms"], ONSET, 900, ramp=5)
    _add(metrics[root]["error_rate"], ONSET, rng.uniform(8, 14), ramp=5)
    for c in TOPOLOGY[root]:
        _scale(metrics[c]["rps"], ONSET, 2.0, ramp=5)
        _add(metrics[c]["p95_latency_ms"], ONSET, 120, ramp=5)
    _propagate(rng, root, metrics, 300, 3, ONSET, ramp=5)
    client = rng.choice(["partner-batch-7", "mobile-app-v9", "crawler-eu-2"])
    logs.append((ONSET + 4, root, "INFO", f"top talker: client_id={client} ({rng.randint(55, 72)}% of requests)"))
    for m in range(ONSET + 3, MINUTES, 3):
        logs.append((m, root, "WARN", "autoscaler at max replicas (12/12), cannot add capacity"))
        logs.append((m, root, "WARN", f"rate limiter shedding load: 429 returned for {rng.randint(12, 30)}% of requests"))


INJECTORS = {"bad_deploy": _bad_deploy, "memory_leak": _memory_leak, "slow_dependency": _slow_dependency,
             "config_error": _config_error, "cert_expiry": _cert_expiry, "traffic_spike": _traffic_spike}


def _make_alert(metrics, now):
    g = metrics["gateway"]
    breach = next((m for m in range(MINUTES) if g["p95_latency_ms"][m] > 500 or g["error_rate"][m] > 1.0), ONSET)
    return (f"ALERT [SEV2] gateway: p95 latency {g['p95_latency_ms'][now]:.0f}ms (SLO 500ms), "
            f"5xx rate {g['error_rate'][now]:.1f}% (SLO 1%). Firing since {ts(breach)} ({now - breach} min). "
            f"Current time {ts(now)}. Find the root cause and recommend remediation.")


def generate(seed: int, fault_type: str | None = None) -> Scenario:
    rng = random.Random(seed)
    fault_type = fault_type or rng.choice(FAULT_TYPES)
    root = rng.choice(ROOT_CANDIDATES[fault_type])
    metrics = _baseline(rng)
    logs = _noise_logs(rng)
    deploys = _benign_deploys(rng, root)
    INJECTORS[fault_type](rng, root, metrics, logs, deploys)
    deploys.sort(key=lambda d: d["minute"])
    logs = [x for x in logs if 0 <= x[0] < MINUTES]
    logs.sort(key=lambda x: x[0])
    for s in SERVICES:
        for m in ("error_rate", "cpu_pct"):
            metrics[s][m] = [min(100.0, v) for v in metrics[s][m]]
    return Scenario(seed=seed, fault_type=fault_type, root_service=root, metrics=metrics, logs=logs,
                    deploys=deploys, alert=_make_alert(metrics, MINUTES - 1))
