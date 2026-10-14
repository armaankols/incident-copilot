"""Run one scenario end to end (shared by the eval harness and the web demo) and grade it."""
from __future__ import annotations

import time
import asyncio

from mcp.shared.memory import create_connected_server_and_client_session

from .agent import build_graph
from .mcp_server import build_server
from .pricing import cost_usd
from .sim import Scenario
from .diagnosis import ACTIONS, insufficient
from .llm import MeteredLLM
from .errors import public_error


from .grading import grade, baseline_latest_deploy


async def run_scenario(sc: Scenario, llm, use_rag: bool = True, max_steps: int = 12, embedder: str = "tfidf", progress: dict | None = None, timeout_s: float = 180,
                       max_tool_requests: int = 32, max_stagnant_steps: int = 3, max_rejections: int = 3,
                       max_output_truncations: int = 3) -> dict:
    t0 = time.perf_counter()
    progress = progress if progress is not None else {}
    progress.update(steps=0, tool_calls=0, model_calls=0, tool_requests=0, cache_hits=0,
                    validation_rejections=0, output_truncations=0, stagnant_steps=0, termination_reason=None, trace=[], billing_uncertain=False,
                    investigation_limits={"model_calls": max_steps, "tool_requests": max_tool_requests,
                                          "stagnant_rounds": max_stagnant_steps, "invalid_submissions": max_rejections,
                                          "output_truncations": max_output_truncations},
                    usage={"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0})
    metered = MeteredLLM(llm, progress, max_steps)
    diagnosis = None
    error = None

    async def investigate():
        server = build_server(sc, use_rag=use_rag, embedder=embedder)
        async with create_connected_server_and_client_session(server) as session:
            listed = await session.list_tools()
            specs = [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema} for t in listed.tools]
            graph = build_graph(metered, session, specs, max_steps=max_steps, progress=progress,
                                max_tool_requests=max_tool_requests, max_stagnant_steps=max_stagnant_steps, max_rejections=max_rejections,
                                max_output_truncations=max_output_truncations)
            return await graph.ainvoke(
                {"messages": [{"role": "user", "content": [{"type": "text", "text": sc.alert}]}], "steps": 0, "pending": [],
                 "diagnosis": None, "usage": dict(progress["usage"]), "tool_calls": 0, "trace": [], "observations": {}, "observation_tools": {},
                 "query_cache": {}, "seen_outputs": [], "tool_requests": 0, "cache_hits": 0, "validation_rejections": 0,
                 "stagnant_steps": 0, "stop_reason": None, "output_truncations": 0},
                config={"recursion_limit": 4 * max_steps + 10})
    try:
        state = await asyncio.wait_for(investigate(), timeout=timeout_s)
        diagnosis = state["diagnosis"]
    except Exception as e:
        error = public_error(e)
        progress["termination_reason"] = "timeout" if isinstance(e, TimeoutError) else "error"
        diagnosis = {**insufficient("Investigation failed; inspect the recorded trace."), "recovery_status": "unavailable", "recovery_reason": "Investigation failed."}
    finally:
        progress["latency_s"] = time.perf_counter() - t0
    return {
        "seed": sc.seed, "fault_type": sc.fault_type, "root_service": sc.root_service,
        "diagnosis": diagnosis, "grade": grade(sc, None if error else diagnosis), "error": error,
        **progress, "cost_usd": cost_usd(getattr(llm, "model", ""), progress["usage"]),
    }
