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
