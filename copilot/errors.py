"""Public error references without copying exception messages into results/logs."""
import logging
import re
import uuid

logger = logging.getLogger(__name__)
CREDIT_MESSAGE = "Live investigations are temporarily unavailable. Please try the offline sample."


class ProviderCreditUnavailable(Exception):
    """A confirmed provider credit rejection, without an uncertain generation charge."""


class ToolFailure(Exception):
    """An MCP error result whose original details must not enter a public trace."""


def credit_unavailable(error):
    if isinstance(error, BaseExceptionGroup):
        return any(credit_unavailable(child) for child in error.exceptions)
    return isinstance(error, ProviderCreditUnavailable)


def public_error(error):
    reference = uuid.uuid4().hex[:16]
    logger.warning("Investigation failure reference=%s exception_type=%s", reference, type(error).__name__)
    message = CREDIT_MESSAGE if credit_unavailable(error) else "Investigation failed"
    return f"{message} (reference: {reference})"


def safe_error(value):
    if isinstance(value, str) and re.fullmatch(
        rf"(?:Investigation failed|{re.escape(CREDIT_MESSAGE)})(?: \(reference: [0-9a-f]{{16}}\))?", value
    ):
        return value
    return "Investigation failed"


def public_result(result):
    """Sanitize historical responses without modifying stored payloads or progress."""
    output = dict(result)
    if output.get("error"):
        output["error"] = safe_error(output["error"])
    if "trace" in output:
        output["trace"] = []
        for event in result["trace"]:
            if event.get("type") == "tool_result" and str(event.get("output", "")).startswith("ERROR:"):
                event = {**event, "output": "ERROR: " + safe_error(event["output"][6:].strip())}
            output["trace"].append(event)
    return output
