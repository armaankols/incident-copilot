"""Offline browser fixture: real graph/MCP, scripted model, no provider calls.

Run: python -m uvicorn scripts.browser_fixture:app --port 8001
Use a separate disposable BUDGET_DB. Never deploy this module.
"""
import asyncio
import os
from copilot.diagnosis import insufficient
from copilot.llm import LLMResponse, ScriptedLLM
import app.main as demo

os.environ["ANTHROPIC_API_KEY"] = "offline-browser-fixture-not-a-real-key"


class BrowserLLM(ScriptedLLM):
    async def complete(self, *args, **kwargs):
        await asyncio.sleep(float(os.getenv("BROWSER_FIXTURE_DELAY", "3")))
        if self.calls == 1:
            if os.getenv("BROWSER_FIXTURE_FAIL") == "1":
                raise RuntimeError("Offline fixture failure after first observation")
            self.calls += 1
            return LLMResponse([{"type": "tool_use", "id": "b", "name": "submit_diagnosis", "input": insufficient("Offline scripted browser check; no model diagnosis measured.")}])
        return await super().complete(*args, **kwargs)


def make_llm(model):
    return BrowserLLM([[{"type": "text", "text": "Offline scripted check: reading service health."},
                        {"type": "tool_use", "id": "a", "name": "list_services", "input": {}}]])


demo.make_llm = make_llm
app = demo.app
