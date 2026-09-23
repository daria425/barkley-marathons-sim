"""Entry point for the ADR-0005 vertical-slice smoke test: `uv run python -m scripts.smoke_test`
(run as a module, not a script, so `sim`/`db`/`agents` resolve from server/ as the root).

setup_observability() must run before `sim.loop` is imported — see observability.py's
docstring for why.
"""

import argparse
import asyncio

from observability import setup_observability

langfuse = setup_observability()

from sim.loop import run  # noqa: E402 (must follow setup_observability(), see module docstring)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Wall-clock speedup, e.g. 60 = 1 sim-minute every real second. Dev convenience "
        "only, per CLAUDE.md — default 1.0 is real Barkley pacing.",
    )
    parser.add_argument(
        "--duration-min",
        type=float,
        default=7.5,
        help="Sim-minutes to run before stopping (ADR-0005's original smoke-test length). Pass "
        "a larger value for a bounded live canary against the real API — see CLAUDE.md.",
    )
    args = parser.parse_args()

    print(
        f"Starting Barkley smoke test — one runner, speed={args.speed}x, "
        f"duration={args.duration_min} sim-min..."
    )
    asyncio.run(run(speed=args.speed, duration_min=args.duration_min))
    langfuse.flush()  # short-lived script — nothing sends without this
