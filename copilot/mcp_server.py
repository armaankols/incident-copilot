"""MCP server exposing incident-investigation tools over one simulated scenario.

Used two ways:
  * in-process by the agent/eval harness (in-memory MCP transport), so the agent really talks MCP
  * standalone over stdio:  python -m copilot.mcp_server --seed 3 --fault memory_leak
    (point Claude Desktop / Claude Code at it and investigate the incident yourself)
"""
from __future__ import annotations

import argparse
import json

from mcp.server.fastmcp import FastMCP

from .retrieval import get_index
from .checks import capacity_check, certificate_check, change_check, fault_check
from .sim import METRICS, MINUTES, SERVICES, TOPOLOGY, Scenario, callers_of, generate, ts


def build_server(sc: Scenario, use_rag: bool = True, embedder: str = "tfidf") -> FastMCP:
    mcp = FastMCP("incident-tools")
    now = sc.now

    @mcp.tool()
    def list_services() -> str:
        """List every service with its dependencies and a snapshot of current health metrics."""
        lines = [f"Time now: {ts(now)}", "service | calls | p95_ms | err% | cpu% | mem_mb | restarts | rps"]
        for s in SERVICES:
            if sc.availability("metrics", s) != "available":
                lines.append(f"{s} | {','.join(TOPOLOGY[s]) or '-'} | telemetry unavailable; health unknown")
                continue
            m = sc.metrics[s]
            lines.append(f"{s} | {','.join(TOPOLOGY[s]) or '-'} | {m['p95_latency_ms'][now]:.0f} | {m['error_rate'][now]:.1f} | "
                         f"{m['cpu_pct'][now]:.0f} | {m['memory_mb'][now]:.0f} | {m['restarts'][now]:.0f} | {m['rps'][now]:.0f}")
        return "\n".join(lines)

    @mcp.tool()
    def query_metrics(service: str, metric: str, minutes: int = 60) -> str:
        """Time series for one metric of one service over the last N minutes (max 120).
        metric is one of: error_rate, p95_latency_ms, cpu_pct, memory_mb, restarts, rps."""
        if service not in SERVICES:
            return f"ERROR: unknown service '{service}'. Valid: {', '.join(SERVICES)}"
        if metric not in METRICS:
            return f"ERROR: unknown metric '{metric}'. Valid: {', '.join(METRICS)}"
        if sc.availability("metrics", service) != "available":
            return f"UNAVAILABLE: {service}.{metric} telemetry is not collected in this snapshot. Health and trend are unknown; no samples returned."
        minutes = max(5, min(int(minutes), MINUTES))
        start = now - minutes + 1
        series = sc.metrics[service][metric][start:now + 1]
        step = max(1, minutes // 12)
        samples = ", ".join(f"{ts(start + i)[:5]}={series[i]:.1f}" for i in range(0, len(series), step))
        return (f"{service}.{metric} last {minutes}m: min={min(series):.1f} mean={sum(series)/len(series):.1f} "
                f"max={max(series):.1f} latest={series[-1]:.1f}\nsamples: {samples}")

    @mcp.tool()
    def search_logs(service: str = "", query: str = "", level: str = "", minutes: int = 120, limit: int = 15) -> str:
        """Search logs. Empty service = all services. query = space-separated terms that must all appear
        (case-insensitive). level = INFO, WARN or ERROR (empty = any). Returns the most recent matches."""
        minutes = max(5, min(int(minutes), MINUTES))
        limit = max(1, min(int(limit), 40))
        terms = query.lower().split()
        if service and service not in SERVICES:
            return f"ERROR: unknown service '{service}'"
        missing = [s for s in ([service] if service else SERVICES) if sc.availability("logs", s) != "available"]
        coverage = ("UNAVAILABLE/PARTIAL: log coverage for " + ", ".join(missing)
                    + ". Absence of matches does not establish health.\n") if missing else ""
        hits = [x for x in sc.logs
                if now - minutes < x[0] <= now and sc.availability("logs", x[1]) != "unavailable"
                and (not service or x[1] == service)
                and (not level or x[2] == level.upper())
                and all(t in x[3].lower() for t in terms)]
        if not hits:
            return coverage + "No log lines matched in available records."
        shown = hits[-limit:]
        out = [f"{ts(m)} {svc} {lvl} {msg}" for m, svc, lvl, msg in shown]
        if len(hits) > len(shown):
            out.insert(0, f"({len(hits)} matches, showing most recent {len(shown)}; narrow with service/level/query)")
        return coverage + "\n".join(out)

    @mcp.tool()
    def check_certificate(service: str) -> str:
        """Assess certificate ownership/expiry from service-local renewal warnings and recent caller peer-verification errors. Returns structured evidence or unknown/conflicting; no live TLS probe. Normal application metrics do not prove a certificate is healthy."""
        logs = sc.logs if all(sc.availability("logs", s) == "available" for s in [service] + callers_of(service)) else []
        return json.dumps(certificate_check(logs, now, service), indent=2)

    @mcp.tool()
    def check_capacity(service: str) -> str:
        """Check recent autoscaler replica headroom for a service from telemetry. Returns headroom, blocked, unknown or conflicting. Does not authorize changing limits or verify infrastructure resources."""
        logs = sc.logs if sc.availability("logs", service) == "available" else []
        return json.dumps(capacity_check(logs, now, service), indent=2)

    @mcp.tool()
    def check_change(service: str, fault_type: str) -> str:
        """Assess bad_deploy or config_error using service-local, release-linked fault evidence. Mere deployment timing, generic errors and missing telemetry are insufficient. Returns supported or unknown; cite a supported assessment before diagnosing either fault. Uses synthetic records, not a causal experiment."""
        available = sc.availability("logs", service) == "available" and sc.availability("deploys") == "available"
        return json.dumps(change_check(sc.logs, sc.deploys, now, service, fault_type, available=available), indent=2)

    @mcp.tool()
    def check_fault(service: str, fault_type: str) -> str:
        """Corroborate memory_leak, slow_dependency or traffic_spike using local fault records and metric trends. Slow dependencies also require recent caller timeouts naming the service. Missing telemetry or generic caller symptoms return unknown. Cite a supported assessment for the exact service/fault before diagnosing; uses narrow synthetic patterns, not causal proof."""
        log_sources = [service] + (callers_of(service) if fault_type == "slow_dependency" else [])
        available = (sc.availability("metrics", service) == "available"
                     and all(sc.availability("logs", s) == "available" for s in log_sources))
        return json.dumps(fault_check(sc.logs, sc.metrics, now, service, fault_type, available=available), indent=2)

    @mcp.tool()
    def get_recent_deploys(hours: float = 2.0) -> str:
        """List deploys and config releases in the last N hours (max 2), newest first."""
        if sc.availability("deploys") != "available":
            return "UNAVAILABLE: deployment/configuration history is not collected in this snapshot. No release history can be inferred."
        window = int(min(hours, 2.0) * 60)
        rows = [d for d in sc.deploys if d["minute"] > now - window]
        if not rows:
            return "No deploys in that window."
        return "\n".join(f"{ts(d['minute'])} ({now - d['minute']} min ago) {d['service']} {d['version']} by {d['author']}: {d['summary']}"
                         for d in reversed(rows))

    if use_rag:
        index = get_index(embedder)

        @mcp.tool()
        def search_runbooks(query: str, k: int = 3) -> str:
            """Vector search (TF-IDF by default) over the team's incident runbooks. Describe symptoms in plain language."""
            hits = index.search(query, max(1, min(int(k), 5)))
            return "\n\n".join(f"[{c.runbook}] (score {s:.2f})\n{c.text}" for c, s in hits)

    return mcp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fault", default=None)
    a = ap.parse_args()
    scenario = generate(a.seed, a.fault)
    import sys
    print(scenario.alert, file=sys.stderr)
    build_server(scenario).run()  # stdio
