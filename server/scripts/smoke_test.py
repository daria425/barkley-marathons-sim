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

import argparse
import asyncio

from dotenv import load_dotenv
from langfuse import get_client
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

load_dotenv()
langfuse = get_client()
AnthropicInstrumentor().instrument()  # before any Anthropic call — auto-traces them to Langfuse

from sim.loop import run  # noqa: E402 (must follow load_dotenv(), see module docstring)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Wall-clock speedup, e.g. 60 = 1 sim-minute every real second. Dev convenience "
        "only, per CLAUDE.md — default 1.0 is real Barkley pacing.",
    )
    args = parser.parse_args()

    print(f"Starting Barkley smoke test — one runner, speed={args.speed}x...")
    asyncio.run(run(speed=args.speed))
    langfuse.flush()  # short-lived script — nothing sends without this
