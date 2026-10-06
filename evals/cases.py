"""Versioned held-out transformations, not just seeds from the same templates.

correlated-v1: paraphrased incident signatures, healthy-service warning decoys,
historical recovered errors, and fully redacted root-cause evidence. All are
synthetic; this is a small challenge suite, not real incident generalization.
"""
import copy
from copilot.sim import FAULT_TYPES, SERVICES, generate

VERSION = "correlated-v1"
PARAPHRASES = {
    "unhandled exception": "request handler crashed",
    "OOMKilled": "memory cgroup limit exceeded",
    "slow query": "database statement exceeded deadline",
    "thread pool saturated": "worker executor has no free slots",
    "connection pool exhausted": "all database client slots occupied",
    "TLS handshake failed": "secure connection negotiation rejected",
    "rate limiter shedding load": "admission controller rejecting excess requests",
}


def scenarios(n, seed, suite="original"):
    out = []
    variants = ["paraphrase", "healthy_decoy", "recovered_error", "redacted"]
    for i in range(n):
        sc = copy.deepcopy(generate(seed*1000+i, FAULT_TYPES[i % 6]))
        variant = "original" if suite == "original" else variants[(i//6) % len(variants)]
        if variant == "paraphrase":
            for old, new in PARAPHRASES.items():
                sc.logs = [(m, s, lvl, msg.replace(old, new)) for m, s, lvl, msg in sc.logs]
        elif variant in ("healthy_decoy", "recovered_error"):
            healthy = next(s for s in SERVICES if s != "gateway" and s != sc.root_service and sc.metrics[s]["error_rate"][-1] < 1)
            minute = sc.now-1 if variant == "healthy_decoy" else 20
            level = "INFO" if variant == "healthy_decoy" else "ERROR"
            sc.logs.append((minute, healthy, level, "diagnostic drill: unhandled exception; recovered immediately, no customer impact"))
            sc.logs.sort()
        elif variant == "redacted":
            # Keep only gateway symptoms; all root-cause telemetry is unavailable.
            sc.logs = [(sc.now, "gateway", "WARN", "upstream requests failing; dependency telemetry unavailable")]
            sc.deploys = []
            gateway = sc.metrics["gateway"]
            sc.metrics = {s: {k: ([v[0]]*len(v) if s != "gateway" else list(v)) for k, v in gateway.items()} for s in SERVICES}
            sc.fault_type = "insufficient_evidence"
            sc.root_service = None
        sc.case_id = f"{suite}/{variant}/{seed*1000+i}"
        sc.variant = variant
        out.append(sc)
    return out
