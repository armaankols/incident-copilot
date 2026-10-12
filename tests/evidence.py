"""Trusted-tool protocol fixtures for isolating validator/recovery behavior.

The telemetry assessments themselves are tested against actual scenarios elsewhere.
"""
import json


def fault_observation(service="search", fault="traffic_spike", status="supported", text="search traffic"):
    return json.dumps(dict(kind="fault", service=service, fault_type=fault, status=status, evidence=[text]))


def add_fault(d, observations, tools):
    observations = {**observations, "obs-fault": fault_observation(d["root_cause_service"], d["fault_type"])}
    tools = {**tools, "obs-fault": "check_fault"}
    d = {**d, "evidence": d["evidence"] + [dict(observation_id="obs-fault", quote='"status": "supported"')]}
    return d, observations, tools
