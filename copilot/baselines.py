"""Simulator-tailored keyword rules. Never read root_service or fault_type.

No claim of generalization: held-out paraphrases intentionally expose shortcuts.
"""
import re
from .diagnosis import insufficient

RULES = [
    ("unhandled exception", "bad_deploy", "rollback"),
    ("OOMKilled", "memory_leak", "restart"),
    ("slow query", "slow_dependency", "optimize_query"),
    ("thread pool saturated", "slow_dependency", "scale"),
    ("connection pool exhausted", "config_error", "restore_config"),
    ("TLS handshake failed", "cert_expiry", "renew_certificate"),
    ("rate limiter shedding load", "traffic_spike", "scale"),
]


def search(sc, query):
    from .sim import ts
    terms = query.lower().split()
    hits = [row for row in sc.logs if row[0] > sc.now-120 and all(t in row[3].lower() for t in terms)]
    return "\n".join(f"{ts(m)} {svc} {level} {msg}" for m, svc, level, msg in hits[-15:])


def predict(search_logs):
    trace = []
    for i, (query, fault, action) in enumerate(RULES, 1):
        text = search_logs(query)
        oid = f"obs-{i}"
        trace.extend([{"type": "tool_call", "tool": "search_logs", "args": {"query": query}},
                      {"type": "tool_result", "tool": "search_logs", "observation_id": oid, "output": text}])
        if not text or text.startswith("No log"):
            continue
        line = next((line for line in reversed(text.splitlines()) if re.match(r"\d\d:\d\d:\d\d ", line)), None)
        if line is None:
            continue
        service = line.split()[1]
        if fault == "cert_expiry":
            match = re.search(r"calling ([a-z]+):", line)
            if not match:
                continue
            service = match.group(1)
        d = dict(status="diagnosed", root_cause_service=service, fault_type=fault,
                 evidence=[{"observation_id": oid, "quote": line}], action=action,
                 target=service, remediation=f"Recommend {action} on {service}; approval and verification required.")
        trace.append({"type": "diagnosis", "args": d})
        return d, trace, i
    d = insufficient("No known log signature matched.")
    trace.append({"type": "diagnosis", "args": d})
    return d, trace, len(RULES)


def baseline_rules(sc):
    return predict(lambda query: search(sc, query))


async def baseline_rules_mcp(sc):
    """Execute the same adaptive rules through the real in-memory MCP transport."""
    from mcp.shared.memory import create_connected_server_and_client_session
    from .mcp_server import build_server
    fetched = {}
    async with create_connected_server_and_client_session(build_server(sc, use_rag=False)) as session:
        for query, _, _ in RULES:
            response = await session.call_tool("search_logs", {"query": query})
            text = "\n".join(c.text for c in response.content if getattr(c, "text", None))
            if response.isError:
                raise RuntimeError(text)
            fetched[query] = text
            d, trace, calls = predict(lambda q: fetched.get(q, ""))
            if d["status"] == "diagnosed":
                return d, trace, len(fetched)
    return predict(lambda q: fetched[q])
