"""LangGraph incident-investigation agent.

Graph:  START -> agent -> (act -> agent)* -> END,  with a `finish` node that returns insufficient evidence if the
step budget runs out. Tools are discovered and executed through an MCP client session, so the agent only
knows tool schemas, never the simulator.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .sim import FAULT_TYPES, SERVICES
from .errors import ToolFailure, public_error

SYSTEM_PROMPT = """You are an expert on-call SRE investigating a production incident in a microservice system.
Use the tools to gather evidence: current health, metrics over time, logs, recent deploys and the team runbooks.
Work efficiently: form a hypothesis, then test it with targeted queries. Do not guess before you have evidence.
Key principle: symptoms appear in callers, the root cause is where the fault ORIGINATES. Pay attention to the
exact minute things changed and compare it with deploys and log timestamps.
Select successful observation IDs in evidence, for example ["obs-12", "obs-13"]. The server attaches exact excerpts from those observations. Do not write quotes, paraphrases or evidence objects. Include the observation ID of the required diagnostic assessment. If rejected, correct the indicated field and resubmit.
Use insufficient_evidence if evidence is missing or ambiguous. A deploy near an error is correlation, not proof of an implementation mechanism. Do not assert a specific cache implementation, code change or previous stable version unless retrieved evidence establishes it. Never infer a rollback version by decrementing a version number.
Unavailable or partial telemetry is unknown, not healthy, empty, or evidence of a configuration error. Do not infer routing/configuration changes from caller symptoms or missing dependency telemetry.
Before diagnosing bad_deploy or config_error, call check_change(service, fault_type) and cite a supported assessment for that exact service and fault, even when action is null. Deployment timing alone is insufficient: bad_deploy needs repeated current local exceptions tied to the latest recorded build; config_error needs loaded configuration and matching local failures. An unknown assessment requires more affirmative evidence or insufficient_evidence, not a different unsupported guess. This narrow check supports synthetic record patterns; it does not establish a specific code defect or prove causality.
If proposing recovery, choose a structured action compatible with the fault and target the root-cause service. Remediation is a recommendation only, not an executed change. The server generates conservative action-specific advice and requires service-policy verification before acting; do not supply concrete commands, unverified versions or invented thresholds.
Before diagnosing memory_leak, slow_dependency or traffic_spike, call check_fault(service, fault_type) and cite its supported assessment for that exact service/fault, even with no action. Local fault records must be corroborated by metrics; slow dependencies also need caller timeouts naming that service. An unknown assessment cannot support a diagnosis. All six fault types require a cited diagnostic assessment.
For certificate expiry, distinguish the caller reporting TLS failure from the peer whose certificate it verifies. The peer can have normal application metrics because rejected handshakes never reach the application. Use check_certificate on the suspected owner and cite an expiry_supported assessment before submitting a certificate diagnosis, even with no recovery action; if ownership or expiry remains unknown/conflicting, abstain.
Before proposing scale, use check_capacity on the target and cite a headroom assessment. At max replicas, or with unknown/conflicting capacity, do not assume permission or resources to raise limits. Keep a supported diagnosis with null action/target rather than guessing another recovery option. Neither operational check executes an action.
Diagnosis and recovery are separate. If the cause is supported but recovery is not verified, submit status=diagnosed with the root service, fault and evidence, and action=null, target=null. Do not discard a supported cause because scaling is blocked. The server will remove an unverified scaling proposal while retaining a valid diagnosis. Certificate ownership evidence is still required even with no action.
Do not repeat identical queries against this fixed incident snapshot. Cached observations keep their original IDs. When further telemetry is unavailable, submit insufficient_evidence rather than repeatedly querying it. Follow the remaining budgets in the user context; repeated results and invalid submissions terminate investigation early.
When ready, call submit_diagnosis directly with no preceding prose. Provide exactly six fields: status, root_cause_service, fault_type, evidence, action, target. Do not write remediation; the server generates it. Use 1-3 unique observation IDs in evidence, including the required diagnostic assessment ID. Do not copy any quotes, metric series or assessment JSON. Abstention uses null cause/action fields and evidence=[]. Only one validated final diagnosis is accepted. Keep investigation updates to one short sentence."""

from .diagnosis import SCHEMA, insufficient, validate_diagnosis

SUBMIT_TOOL = {"name": "submit_diagnosis", "description": "Submit an evidence-backed diagnosis or insufficient_evidence. Actions are recommendations only.", "input_schema": SCHEMA}


class AgentState(TypedDict):
    messages: list[dict]
    steps: int
    pending: list[dict]
    diagnosis: dict | None
    usage: dict
    tool_calls: int
    trace: list[dict]
    observations: dict
    observation_tools: dict
    query_cache: dict
    seen_outputs: list[str]
    tool_requests: int
    cache_hits: int
    validation_rejections: int
    stagnant_steps: int
    stop_reason: str | None
    output_truncations: int


def _add_usage(usage: dict, resp) -> dict:
    return {"input_tokens": usage["input_tokens"] + resp.input_tokens,
            "output_tokens": usage["output_tokens"] + resp.output_tokens,
            "cache_read_tokens": usage["cache_read_tokens"] + resp.cache_read_tokens,
            "cache_write_tokens": usage["cache_write_tokens"] + resp.cache_write_tokens}


def _append_user(messages: list[dict], blocks: list[dict]) -> list[dict]:
    if messages and messages[-1]["role"] == "user":
        merged = dict(messages[-1])
        merged["content"] = list(merged["content"]) + blocks
        return messages[:-1] + [merged]
    return messages + [{"role": "user", "content": blocks}]


def build_graph(llm, session, tool_specs: list[dict], max_steps: int = 12, progress: dict | None = None,
                max_tool_requests: int = 32, max_stagnant_steps: int = 3, max_rejections: int = 3,
                max_output_truncations: int = 3):
    if min(max_steps, max_tool_requests, max_stagnant_steps, max_rejections, max_output_truncations) < 1:
        raise ValueError("Investigation limits must be positive")
    progress = progress if progress is not None else {}

    def record(event):
        progress.setdefault("trace", []).append(event)
    all_tools = tool_specs + [SUBMIT_TOOL]
    defaults = {t["name"]: {k: v["default"] for k, v in t.get("input_schema", {}).get("properties", {}).items()
                             if "default" in v} for t in tool_specs}

    async def agent_node(state: AgentState) -> dict[str, Any]:
        budget = (f"Remaining model calls including this call: {max_steps-state['steps']}; "
                  f"tool requests: {max(0, max_tool_requests-state.get('tool_requests', 0))}; "
                  f"invalid submissions allowed before stopping: {max_rejections-state.get('validation_rejections', 0)}. "
                  f"output truncations allowed before stopping: {max_output_truncations-state.get('output_truncations', 0)}. "
                  f"Consecutive rounds without new tool output: {state.get('stagnant_steps', 0)}/{max_stagnant_steps}. "
                  "Submit a supported diagnosis with null recovery fields if no action is verified, or abstain when diagnostic evidence is insufficient.")
        call_messages = _append_user(state["messages"], [{"type": "text", "text": budget}])
        resp = await llm.complete(SYSTEM_PROMPT, call_messages, all_tools)
        trace = list(state["trace"])
        for b in resp.content:
            if b["type"] == "text" and b["text"].strip():
                trace.append({"type": "investigation_update", "text": b["text"].strip()})
        progress["steps"] = state["steps"] + 1
        for event in trace[len(state["trace"]):]:
            record(event)
        pending = [b for b in resp.content if b["type"] == "tool_use"]
        messages = call_messages + [{"role": "assistant", "content": resp.content or [{"type": "text", "text": "..."}]}]
        truncations = state.get("output_truncations", 0)
        if resp.stop_reason == "max_tokens":
            truncations += 1
            event = {"type": "output_truncated", "output_tokens": resp.output_tokens,
                     "skipped_tools": [b["name"] for b in pending],
                     "output": "Response reached its output limit. No tools or diagnosis from this response were executed."}
            trace.append(event); record(event)
            feedback = ("Output was truncated. No tools were executed. Submit a compact complete response without preceding prose: "
                        "six fields (status, root_cause_service, fault_type, evidence, action, target), "
                        '1-3 observation IDs in evidence (e.g. ["obs-12"]), no quotes or remediation. Abstain if required diagnostic evidence is unavailable.')
            closures = [{"type": "tool_result", "tool_use_id": b["id"], "content": feedback, "is_error": True} for b in pending]
            messages = _append_user(messages, closures or [{"type": "text", "text": feedback}])
            progress["output_truncations"] = truncations
            return {"messages": messages, "pending": [], "steps": state["steps"]+1,
                    "output_truncations": truncations, "stop_reason": "output_limit" if truncations >= max_output_truncations else None,
                    "usage": _add_usage(state["usage"], resp), "trace": trace}
        if not pending:
            messages = _append_user(messages, [{"type": "text", "text": "Continue investigating with tools, or call submit_diagnosis."}])
        stagnant = state.get("stagnant_steps", 0) + (0 if pending else 1)
        progress["stagnant_steps"] = stagnant
        return {"messages": messages, "pending": pending, "steps": state["steps"] + 1,
                "stagnant_steps": stagnant, "stop_reason": "stagnation" if not pending and stagnant >= max_stagnant_steps else None,
                "usage": _add_usage(state["usage"], resp), "trace": trace, "output_truncations": truncations}

    async def act_node(state: AgentState) -> dict[str, Any]:
        results, trace, diagnosis, n_calls = [], list(state["trace"]), state["diagnosis"], 0
        observations = dict(state["observations"])
        observation_tools = dict(state.get("observation_tools", {}))
        cache = dict(state.get("query_cache", {}))
        seen = set(state.get("seen_outputs", []))
        requests, hits = state.get("tool_requests", 0), state.get("cache_hits", 0)
        rejections, new_information = state.get("validation_rejections", 0), False
        for call in state["pending"]:
            name, args = call["name"], call["input"]
            if name == "submit_diagnosis":
                try:
                    if diagnosis is not None:
                        raise ValueError("Only one final diagnosis is accepted")
                    diagnosis = validate_diagnosis(args, observations, observation_tools)
                    event = {"type": "diagnosis", "args": diagnosis}
                    trace.append(event)
                    record(event)
                    text = "Diagnosis recorded."
                except ValueError as e:
                    rejections += 1
                    progress["validation_rejections"] = rejections
                    text = f"ERROR: {e}"
                    event = {"type": "validation_error", "output": text}
                    trace.append(event)
                    record(event)
            else:
                requests += 1
                progress["tool_requests"] = requests
                if diagnosis is not None or requests > max_tool_requests:
                    text = "ERROR: Investigation finalized or tool-request limit reached. No tool executed."
                    event = {"type": "tool_skipped", "tool": name, "args": args, "output": text}
                    trace.append(event); record(event)
                    results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text})
                    continue
                if not isinstance(args, dict):
                    text = "ERROR: Tool input must be an object. No tool executed."
                    event = {"type": "tool_skipped", "tool": name, "args": args, "output": text}
                    trace.append(event); record(event)
                    results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text})
                    continue
                key = name + ":" + json.dumps({**defaults.get(name, {}), **args}, sort_keys=True)
                if key in cache:
                    oid, output = cache[key]
                    hits += 1
                    progress["cache_hits"] = hits
                    event = {"type": "tool_cache_hit", "tool": name, "args": args, "observation_id": oid}
                    trace.append(event); record(event)
                    results.append({"type": "tool_result", "tool_use_id": call["id"],
                                    "content": f"Reused observation from this fixed snapshot. Observation ID: {oid}\n{output}"})
                    continue
                n_calls += 1
                event = {"type": "tool_call", "tool": name, "args": args}
                trace.append(event)
                record(event)
                progress["tool_calls"] = state["tool_calls"] + n_calls
                try:
                    r = await session.call_tool(name, args)
                    text = "\n".join(c.text for c in r.content if getattr(c, "text", None))
                    if r.isError:
                        text = "ERROR: " + public_error(ToolFailure())
                except Exception as e:  # noqa: BLE001
                    text = "ERROR: " + public_error(e)
                text = text[:6000]
                oid = f"obs-{state['tool_calls'] + n_calls}"
                if text and not text.startswith("ERROR:"):
                    observations[oid] = text
                    observation_tools[oid] = name
                    cache[key] = (oid, text)
                    fingerprint = hashlib.sha256((name + "\n" + text).encode()).hexdigest()
                    new_information = new_information or fingerprint not in seen
                    seen.add(fingerprint)
                event = {"type": "tool_result", "tool": name, "observation_id": oid, "output": text}
                trace.append(event)
                record(event)
                text = f"Observation ID: {oid}\n{text}"
            results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text})
        stagnant = 0 if new_information else state.get("stagnant_steps", 0) + 1
        stop = ("correction_limit" if rejections >= max_rejections else "tool_limit" if requests >= max_tool_requests
                else "stagnation" if stagnant >= max_stagnant_steps else None)
        progress.update(tool_requests=requests, cache_hits=hits, validation_rejections=rejections,
                        stagnant_steps=stagnant)
        if diagnosis is not None:
            progress["termination_reason"] = "model_submission"
        return {"messages": _append_user(state["messages"], results), "pending": [], "diagnosis": diagnosis,
                "tool_calls": state["tool_calls"] + n_calls, "trace": trace, "observations": observations,
                "observation_tools": observation_tools, "query_cache": cache, "seen_outputs": sorted(seen),
                "tool_requests": requests, "cache_hits": hits, "validation_rejections": rejections,
                "stagnant_steps": stagnant, "stop_reason": stop}

    async def finish_node(state: AgentState) -> dict[str, Any]:
        reason = state.get("stop_reason") or "step_budget"
        explanations = {"step_budget": "Investigation model-call budget exhausted.",
                        "stagnation": "Investigation stopped after repeated rounds without new tool output.",
                        "correction_limit": "Investigation stopped after repeated invalid submissions.",
                        "output_limit": "Investigation stopped after repeated output truncation.",
                        "tool_limit": "Investigation tool-request limit reached."}
        diagnosis = {**insufficient(explanations[reason]), "recovery_status": "unavailable", "recovery_reason": explanations[reason]}
        progress["termination_reason"] = reason
        event = {"type": "diagnosis", "args": diagnosis, "budget_exhausted": reason == "step_budget", "termination_reason": reason}
        record(event)
        return {"diagnosis": diagnosis, "trace": state["trace"] + [event]}

    def after_agent(state: AgentState) -> str:
        if state["pending"]:
            return "act"
        return "finish" if state.get("stop_reason") or state["steps"] >= max_steps else "agent"

    def after_act(state: AgentState) -> str:
        if state["diagnosis"]:
            return END
        return "finish" if state.get("stop_reason") or state["steps"] >= max_steps else "agent"

    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("act", act_node)
    g.add_node("finish", finish_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", after_agent, {"act": "act", "agent": "agent", "finish": "finish"})
    g.add_conditional_edges("act", after_act, {END: END, "agent": "agent", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile()
