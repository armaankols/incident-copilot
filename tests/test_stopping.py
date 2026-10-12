import asyncio
import copy

import pytest

from copilot.diagnosis import insufficient, validate_diagnosis
from copilot.llm import ScriptedLLM
from copilot.runner import run_scenario
from copilot.sim import generate
from evals.run_evals import summarize
from tests.evidence import fault_observation


def candidate():
    return dict(status="diagnosed", root_cause_service="search", fault_type="traffic_spike",
                action=None, target=None, evidence=[dict(observation_id="obs-1", quote="search traffic")],
                remediation="Invented instructions")


def tool(name="list_services", args=None, id="t"):
    return dict(type="tool_use", id=id, name=name, input=args or {})


def test_supported_diagnosis_without_action_is_retained_and_scored_separately():
    d = candidate()
    result = validate_diagnosis(d, {"obs-1": fault_observation()}, {"obs-1": "check_fault"})
    assert d["remediation"] == "Invented instructions"
    assert result["status"] == "diagnosed" and result["root_cause_service"] == "search"
    assert result["action"] is None and result["recovery_status"] == "unverified"
    from copilot.grading import grade
    g = grade(generate(5, "traffic_spike"), result)
    assert g["both_ok"] and not g["remediation_ok"]


@pytest.mark.parametrize("changes", [dict(target="search"), dict(action="scale"), dict(evidence=[])])
def test_no_action_path_does_not_bypass_structure_or_evidence(changes):
    with pytest.raises(ValueError):
        validate_diagnosis({**candidate(), **changes}, {"obs-1": "search traffic"})


def test_no_action_cannot_bypass_certificate_ownership():
    d = {**candidate(), "fault_type": "cert_expiry"}
    with pytest.raises(ValueError, match="check_certificate"):
        validate_diagnosis(d, {"obs-1": "search traffic"})


def test_repeated_queries_reuse_original_observation_then_stop_without_extra_call():
    llm = ScriptedLLM([[tool()]])
    r = asyncio.run(run_scenario(generate(1), llm))
    assert r["termination_reason"] == "stagnation"
    assert r["diagnosis"]["status"] == "insufficient_evidence"
    assert r["model_calls"] == llm.calls == 4
    assert r["tool_calls"] == 1 and r["tool_requests"] == 4 and r["cache_hits"] == 3
    assert {e["observation_id"] for e in r["trace"] if e["type"] == "tool_cache_hit"} == {"obs-1"}
    assert not r["trace"][-1]["budget_exhausted"]


def test_equivalent_defaults_hit_cache_and_cached_evidence_remains_citable():
    d = {**candidate(), "evidence": [dict(observation_id="obs-1", quote="search.rps"),
         dict(observation_id="obs-2", quote='"status": "supported"')]}
    llm = ScriptedLLM([
        [tool("query_metrics", dict(service="search", metric="rps"), "a"),
         tool("check_fault", dict(service="search", fault_type="traffic_spike"), "fault")],
        [tool("query_metrics", dict(service="search", metric="rps", minutes=60), "b")],
        [tool("submit_diagnosis", d, "d")],
    ])
    r = asyncio.run(run_scenario(generate(5, "traffic_spike"), llm))
    assert r["grade"]["both_ok"] and r["tool_calls"] == 2 and r["cache_hits"] == 1
    assert r["termination_reason"] == "model_submission"


def test_new_output_resets_stagnation_and_allows_diagnosis():
    d = {**candidate(), "evidence": [dict(observation_id="obs-2", quote='"status": "supported"')]}
    llm = ScriptedLLM([[tool()], [tool()], [tool()],
                       [tool("check_fault", dict(service="search", fault_type="traffic_spike"))],
                       [tool("submit_diagnosis", d)]])
    r = asyncio.run(run_scenario(generate(5, "traffic_spike"), llm))
    assert r["grade"]["both_ok"] and r["model_calls"] == 5 and r["tool_calls"] == 2


def test_repeated_invalid_submissions_stop_before_global_model_budget():
    d = {**candidate(), "evidence": [dict(observation_id="obs-99", quote="invented")]}
    llm = ScriptedLLM([[tool()], [tool("submit_diagnosis", d)]])
    r = asyncio.run(run_scenario(generate(1), llm))
    assert r["termination_reason"] == "correction_limit"
    assert r["validation_rejections"] == 3 and r["model_calls"] == llm.calls == 4
    assert r["diagnosis"]["root_cause_service"] is None


def test_large_tool_batch_is_closed_without_exceeding_request_limit():
    llm = ScriptedLLM([[tool("query_metrics", dict(service="search", metric=m), m)
                        for m in ("rps", "cpu_pct", "memory_mb", "error_rate")]])
    r = asyncio.run(run_scenario(generate(5, "traffic_spike"), llm, max_tool_requests=2))
    assert r["termination_reason"] == "tool_limit" and r["model_calls"] == 1
    assert r["tool_calls"] == 2 and r["tool_requests"] == 4
    assert sum(e["type"] == "tool_skipped" for e in r["trace"]) == 2


def test_no_tools_execute_after_accepted_diagnosis_in_same_batch():
    llm = ScriptedLLM([[tool("submit_diagnosis", insufficient()), tool()]])
    r = asyncio.run(run_scenario(generate(1), llm))
    assert r["termination_reason"] == "model_submission" and r["tool_calls"] == 0


def test_malformed_tool_input_stops_cleanly_without_mcp_execution():
    bad = dict(type="tool_use", id="bad", name="list_services", input=None)
    r = asyncio.run(run_scenario(generate(1), ScriptedLLM([[bad]])))
    assert r["error"] is None and r["termination_reason"] == "stagnation"
    assert r["tool_calls"] == 0 and r["model_calls"] == 3


def test_malformed_trailing_tool_cannot_erase_accepted_result():
    bad = dict(type="tool_use", id="bad", name="list_services", input=None)
    r = asyncio.run(run_scenario(generate(1), ScriptedLLM([[tool("submit_diagnosis", insufficient()), bad]])))
    assert r["error"] is None and r["termination_reason"] == "model_submission"
    assert r["tool_calls"] == 0


def test_completion_metrics_distinguish_model_and_forced_abstention():
    llm = ScriptedLLM([[tool("submit_diagnosis", insufficient())]])
    model = asyncio.run(run_scenario(generate(1), llm))
    forced = asyncio.run(run_scenario(generate(1), ScriptedLLM([[tool()]])))
    summary = summarize([model, forced])
    assert summary["model_submitted_abstentions"] == 1 and summary["forced_abstentions"] == 1
    assert summary["finalization_counts"] == {"model_submission": 1, "stagnation": 1}


def test_model_receives_remaining_budgets_without_secret_state():
    class Capture(ScriptedLLM):
        async def complete(self, system, messages, tools, tool_choice=None):
            self.messages = copy.deepcopy(messages)
            return await super().complete(system, messages, tools, tool_choice)
    llm = Capture([[tool("submit_diagnosis", insufficient())]])
    asyncio.run(run_scenario(generate(1), llm, max_steps=6, max_tool_requests=10))
    context = llm.messages[-1]["content"][-1]["text"]
    assert "including this call: 6" in context and "tool requests: 10" in context
    assert "root_service" not in context
