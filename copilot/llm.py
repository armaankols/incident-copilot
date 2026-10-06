"""Thin LLM layer. AnthropicLLM calls the Messages API with tool use; ScriptedLLM replays canned
responses so the graph, MCP plumbing and harness can be tested offline without an API key."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: list[dict]
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int = 1000, max_input_tokens: int = 24000):
        import anthropic
        self.model = model
        self.max_tokens = max_tokens
        self.max_input_tokens = max_input_tokens
        self.client = anthropic.AsyncAnthropic(max_retries=0, timeout=45.0)

    async def complete(self, system: str, messages: list[dict], tools: list[dict], tool_choice: dict | None = None) -> LLMResponse:
        kwargs = dict(
            model=self.model, max_tokens=self.max_tokens, messages=messages, tools=tools,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        )
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        counted = await self.client.messages.count_tokens(model=self.model, system=kwargs["system"], messages=messages, tools=tools)
        if counted.input_tokens > self.max_input_tokens:
            raise ValueError("Per-call input token budget exceeded")
        resp = await self.client.messages.create(**kwargs)
        blocks = []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        u = resp.usage
        return LLMResponse(blocks, resp.stop_reason, u.input_tokens, u.output_tokens,
                           getattr(u, "cache_read_input_tokens", 0) or 0,
                           getattr(u, "cache_creation_input_tokens", 0) or 0)


@dataclass
class ScriptedLLM:
    """Replays a fixed list of responses (each a list of content blocks). For tests only."""
    script: list[list[dict]]
    calls: int = field(default=0)
    model: str = "scripted"

    async def complete(self, system, messages, tools, tool_choice=None) -> LLMResponse:
        idx = min(self.calls, len(self.script) - 1)
        self.calls += 1
        return LLMResponse(self.script[idx], "tool_use", input_tokens=1000, output_tokens=100)


class MeteredLLM:
    """Capture usage as responses arrive, including calls followed by graph failure."""
    def __init__(self, llm, progress, max_calls):
        self.llm, self.progress, self.max_calls = llm, progress, max_calls
        self.model = llm.model

    async def complete(self, *args, **kwargs):
        if self.progress["model_calls"] >= self.max_calls:
            raise ValueError("Model call budget exceeded")
        self.progress["model_calls"] += 1
        try:
            response = await self.llm.complete(*args, **kwargs)
        except BaseException:
            # A timeout/disconnect may have reached the provider without a usage response.
            self.progress["billing_uncertain"] = isinstance(self.llm, AnthropicLLM)
            raise
        for key in self.progress["usage"]:
            self.progress["usage"][key] += getattr(response, key)
        return response
