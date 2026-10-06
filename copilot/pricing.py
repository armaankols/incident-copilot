"""USD per million tokens (input, output). VERIFY against Anthropic's pricing page before quoting costs."""
PRICES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5-5": (2.0, 10.0),
}
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def cost_usd(model: str, usage: dict) -> float:
    if model == "scripted":
        return 0.0
    if model not in PRICES:
        raise ValueError(f"Unknown model price: {model}")
    pin, pout = PRICES[model]
    return (usage.get("input_tokens", 0) * pin
            + usage.get("cache_write_tokens", 0) * pin * 1.25
            + usage.get("cache_read_tokens", 0) * pin * 0.1
            + usage.get("output_tokens", 0) * pout) / 1_000_000
