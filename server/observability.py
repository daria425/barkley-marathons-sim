"""Shared startup wiring for Anthropic/Langfuse observability — extracted from
scripts/smoke_test.py so main.py doesn't duplicate it.

Must run before `sim.loop` (or anything importing agents.participant) is imported:
agents/participant.py constructs the AsyncAnthropic client at import time, which reads
ANTHROPIC_API_KEY from the environment right then, not lazily on first call. So callers
call setup_observability() at their own module top, before importing sim.loop — a FastAPI
startup/lifespan hook would run too late, after that import already happened.

get_client() must run before AnthropicInstrumentor().instrument(): get_client() is what
registers Langfuse's OTel TracerProvider globally — instrumenting first silently traces to
nowhere (confirmed empirically: swapping the order was the difference between an empty
Langfuse project and a real trace showing up).
"""

from dotenv import load_dotenv
from langfuse import get_client
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor


def setup_observability() -> None:
    load_dotenv()
    langfuse = get_client()
    # before any Anthropic call — auto-traces to Langfuse
    AnthropicInstrumentor().instrument()
    return langfuse
