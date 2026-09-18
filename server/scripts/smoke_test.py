"""Entry point for the ADR-0005 vertical-slice smoke test: `uv run python -m scripts.smoke_test`
(run as a module, not a script, so `sim`/`db`/`agents` resolve from server/ as the root).

load_dotenv() must run before `sim.loop` is imported: agents/participant.py constructs the
AsyncAnthropic client at import time, which reads ANTHROPIC_API_KEY from the environment
right then, not lazily on first call.

get_client() must run before AnthropicInstrumentor().instrument(): get_client() is what
registers Langfuse's OTel TracerProvider globally — instrumenting first silently traces to
nowhere (confirmed empirically: swapping the order was the difference between an empty
Langfuse project and a real trace showing up).
"""

import asyncio

from dotenv import load_dotenv
from langfuse import get_client
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

load_dotenv()
langfuse = get_client()
AnthropicInstrumentor().instrument()  # before any Anthropic call — auto-traces them to Langfuse

from sim.loop import run  # noqa: E402 (must follow load_dotenv(), see module docstring)

if __name__ == "__main__":
    print("Starting Barkley smoke test — 1 sim-minute, real time, one runner...")
    asyncio.run(run())
    langfuse.flush()  # short-lived script — nothing sends without this
