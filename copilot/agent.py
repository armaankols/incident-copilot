"""LangGraph incident-investigation agent.

Graph:  START -> agent -> (act -> agent)* -> END,  with a `finish` node that returns insufficient evidence if the
step budget runs out. Tools are discovered and executed through an MCP client session, so the agent only
knows tool schemas, never the simulator.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .sim import FAULT_TYPES, SERVICES

SYSTEM_PROMPT = """You are an expert on-call SRE investigating a production incident in a microservice system.
Use the tools to gather evidence: current health, metrics over time, logs, recent deploys and the team runbooks.
Work efficiently: form a hypothesis, then test it with targeted queries. Do not guess before you have evidence.
Key principle: symptoms appear in callers, the root cause is where the fault ORIGINATES. Pay attention to the
exact minute things changed and compare it with deploys and log timestamps.
Cite observation_id and exact quote from successful tool outputs. Use insufficient_evidence if evidence is missing or ambiguous. Choose a structured action and target; remediation is a recommendation only. When you are confident, call submit_diagnosis exactly once. Do not write long prose answers."""

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


def build_graph(llm, session, tool_specs: list[dict], max_steps: int = 12, progress: dict | None = None):
    if max_steps < 1:
        raise ValueError("max_steps must be positive")
    progress = progress if progress is not None else {}

    def record(event):
        progress.setdefault("trace", []).append(event)
    all_tools = tool_specs + [SUBMIT_TOOL]

    async def agent_node(state: AgentState) -> dict[str, Any]:
        resp = await llm.complete(SYSTEM_PROMPT, state["messages"], all_tools)
        trace = list(state["trace"])
        for b in resp.content:
            if b["type"] == "text" and b["text"].strip():
                trace.append({"type": "investigation_update", "text": b["text"].strip()})
        progress["steps"] = state["steps"] + 1
        for event in trace[len(state["trace"]):]:
            record(event)
        pending = [b for b in resp.content if b["type"] == "tool_use"]
        messages = state["messages"] + [{"role": "assistant", "content": resp.content or [{"type": "text", "text": "..."}]}]
        if not pending:
            messages = _append_user(messages, [{"type": "text", "text": "Continue investigating with tools, or call submit_diagnosis."}])
        return {"messages": messages, "pending": pending, "steps": state["steps"] + 1,
                "usage": _add_usage(state["usage"], resp), "trace": trace}

    async def act_node(state: AgentState) -> dict[str, Any]:
        results, trace, diagnosis, n_calls = [], list(state["trace"]), state["diagnosis"], 0
        observations = dict(state["observations"])
        for call in state["pending"]:
            name, args = call["name"], call["input"]
            if name == "submit_diagnosis":
                try:
                    if diagnosis is not None:
                        raise ValueError("Only one final diagnosis is accepted")
                    diagnosis = validate_diagnosis(args, observations)
                    event = {"type": "diagnosis", "args": diagnosis}
                    trace.append(event)
                    record(event)
                    text = "Diagnosis recorded."
                except ValueError as e:
                    text = f"ERROR: {e}"
                    event = {"type": "validation_error", "output": text}
                    trace.append(event)
                    record(event)
            else:
                n_calls += 1
                event = {"type": "tool_call", "tool": name, "args": args}
                trace.append(event)
                record(event)
                progress["tool_calls"] = state["tool_calls"] + n_calls
                try:
                    r = await session.call_tool(name, args)
                    text = "\n".join(c.text for c in r.content if getattr(c, "text", None))
                    if r.isError:
                        text = "ERROR: " + text
                except Exception as e:  # noqa: BLE001
                    text = f"ERROR: {e}"
                text = text[:6000]
                oid = f"obs-{state['tool_calls'] + n_calls}"
                if text and not text.startswith("ERROR:"):
                    observations[oid] = text
                event = {"type": "tool_result", "tool": name, "observation_id": oid, "output": text}
                trace.append(event)
                record(event)
                text = f"Observation ID: {oid}\n{text}"
            results.append({"type": "tool_result", "tool_use_id": call["id"], "content": text})
        return {"messages": _append_user(state["messages"], results), "pending": [], "diagnosis": diagnosis,
                "tool_calls": state["tool_calls"] + n_calls, "trace": trace, "observations": observations}

    async def finish_node(state: AgentState) -> dict[str, Any]:
        diagnosis = insufficient()
        event = {"type": "diagnosis", "args": diagnosis, "budget_exhausted": True}
        record(event)
        return {"diagnosis": diagnosis, "trace": state["trace"] + [event]}

    def after_agent(state: AgentState) -> str:
        if state["pending"]:
            return "act"
        return "finish" if state["steps"] >= max_steps else "agent"

    def after_act(state: AgentState) -> str:
        if state["diagnosis"]:
            return END
        return "finish" if state["steps"] >= max_steps else "agent"

    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("act", act_node)
    g.add_node("finish", finish_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", after_agent, {"act": "act", "agent": "agent", "finish": "finish"})
    g.add_conditional_edges("act", after_act, {END: END, "agent": "agent", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile()
