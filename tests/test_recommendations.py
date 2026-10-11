"""Adversarial recommendation and citation checks; no provider calls."""
import asyncio
import copy

import pytest

from copilot.diagnosis import insufficient, validate_diagnosis
from copilot.llm import ScriptedLLM
from copilot.runner import run_scenario
from copilot.sim import generate


def candidate():
    return dict(status="diagnosed", root_cause_service="payments", fault_type="memory_leak",
                action="rollback", target="payments",
                evidence=[dict(observation_id="obs-1", quote="OOMKilled")],
                remediation="Roll back to v3.1.8 immediately; an unbounded cache guarantees another OOMKill.")


def test_unsupported_recovery_specifics_cannot_reach_accepted_recommendation():
    proposed = candidate()
    original = copy.deepcopy(proposed)
    accepted = validate_diagnosis(proposed, {"obs-1": "payments ERROR OOMKilled"})
    assert proposed == original  # The recorded provider response stays unchanged.
    assert accepted["evidence"] == proposed["evidence"]
    assert accepted["action"] == "rollback" and accepted["target"] == "payments"
    advice = accepted["remediation"]
    assert "v3.1.8" not in advice and "unbounded cache" not in advice
    assert "previous healthy release" in advice and "compatibility" in advice
    assert "has not been verified" in advice and "no change has been executed" in advice


def test_abstention_does_not_publish_provider_recovery_advice():
    accepted = validate_diagnosis(insufficient("Immediately roll back payments to v3.1.8"), {})
    assert accepted["action"] is None and accepted["target"] is None
    assert "v3.1.8" not in accepted["remediation"]
    assert "Insufficient evidence to recommend" in accepted["remediation"]


@pytest.mark.parametrize("updates", [dict(action="renew_certificate"), dict(target="auth")])
def test_incompatible_recovery_action_or_wrong_service_is_rejected(updates):
    with pytest.raises(ValueError):
        validate_diagnosis({**candidate(), **updates}, {"obs-1": "OOMKilled"})


def test_unavailable_observation_feedback_names_available_sources():
    d = candidate()
    d["evidence"] = [dict(observation_id="obs-99", quote="OOMKilled")]
    with pytest.raises(ValueError, match="Successful observation IDs: obs-1"):
        validate_diagnosis(d, {"obs-1": "OOMKilled"})


def test_paraphrased_citation_feedback_identifies_source_and_correction():
    d = candidate()
    d["evidence"] = [dict(observation_id="obs-1", quote="out of memory")]
    with pytest.raises(ValueError, match="Quote for obs-1.*Copy a contiguous excerpt verbatim"):
        validate_diagnosis(d, {"obs-1": "OOMKilled"})


def test_graph_returns_actionable_feedback_and_sanitizes_corrected_diagnosis():
    sc = generate(1, "memory_leak")
    d = {**candidate(), "root_cause_service": sc.root_service, "target": sc.root_service,
         "evidence": [dict(observation_id="obs-1", quote="invented health") ]}
    corrected = {**d, "evidence": [dict(observation_id="obs-1", quote="Time now:")]}
    class CapturingLLM(ScriptedLLM):
        async def complete(self, system, messages, tools, tool_choice=None):
            self.last_messages = copy.deepcopy(messages)
            return await super().complete(system, messages, tools, tool_choice)
    llm = CapturingLLM([
        [dict(type="tool_use", id="health", name="list_services", input={})],
        [dict(type="tool_use", id="bad", name="submit_diagnosis", input=d)],
        [dict(type="tool_use", id="fixed", name="submit_diagnosis", input=corrected)],
    ])
    result = asyncio.run(run_scenario(sc, llm, max_steps=3))
    assert result["error"] is None and result["diagnosis"]["status"] == "diagnosed"
    assert result["model_calls"] == 3 and result["tool_calls"] == 1
    feedback = llm.last_messages[-1]["content"][0]["content"]
    assert "Quote for obs-1" in feedback and "Copy a contiguous excerpt verbatim" in feedback
    assert "v3.1.8" not in result["diagnosis"]["remediation"]
    accepted_event = next(e for e in result["trace"] if e["type"] == "diagnosis")
    assert accepted_event["args"] == result["diagnosis"]
