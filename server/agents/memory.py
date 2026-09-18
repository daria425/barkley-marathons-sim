"""Sliding-window history for brain prompts, per CLAUDE.md's Memory and persistence section.

Each brain call should get the last N Observation/Decision pairs verbatim, plus a running
summary of anything older, compressed by an LLM call (not code) when history exceeds N. This
module builds the sliding-window replay for real. Autocompaction is NOT implemented here yet
— CLAUDE.md scopes the summary/compaction machinery to phase 2 ("right after v1"), and this
smoke test's window (N=20, ~12 ticks max) never actually exceeds N, so there's nothing to
exercise it against. `compact_if_needed` raises rather than silently no-op-ing, so whoever
wires up a longer-running loop later hits an explicit TODO instead of quietly losing history.
"""

from models import Decision, Observation

SLIDING_WINDOW_N = 20  # CLAUDE.md's real-race spec says N=10; smoke test uses 20, revisit later


def format_observation(obs: Observation) -> str:
    """Render an Observation as plain text, framed as the runner's own perception ("your
    body and surroundings"), not as someone speaking to them — the `user` role just carries
    this turn's input per the API's user/assistant/system roles, it doesn't imply a person is
    addressing the persona."""
    lines = [
        "Your body and surroundings, right now:",
        f"{obs.clock_time} ({obs.elapsed_min} min elapsed), loop {obs.loop}, "
        f"{obs.books_found} books found.",
        f"HR {obs.hr}, pace {obs.pace_min_per_km:.1f} min/km, cadence {obs.cadence}.",
        f"You feel: {obs.feel}. Last ate {obs.last_ate_min_ago} min ago.",
        f"Bearing {obs.bearing_deg:.0f} degrees. Believed position: {obs.gps_guess}.",
        f"Terrain: {obs.terrain}. Weather: {obs.weather}.",
    ]
    return "\n".join(lines)


def turns_to_messages(turns: list[tuple[Observation, Decision]]) -> list[dict]:
    """Replay past turns as alternating user/assistant messages so the model sees its own
    prior reasoning, not just a fresh Observation every call. `turns` must be oldest-first
    (db.get_recent_turns already returns them that way)."""
    messages = []
    for obs, decision in turns:
        messages.append({"role": "user", "content": format_observation(obs)})
        messages.append({"role": "assistant", "content": decision.model_dump_json()})
    return messages


def compact_if_needed(turn_count: int) -> None:
    """Placeholder for CLAUDE.md's LLM-driven autocompaction. Called by the loop so the
    "not implemented yet" fact is loud instead of turns silently falling off the window."""
    if turn_count > SLIDING_WINDOW_N:
        raise NotImplementedError(
            f"History ({turn_count} turns) exceeds SLIDING_WINDOW_N ({SLIDING_WINDOW_N}) — "
            "autocompaction isn't built yet (CLAUDE.md phase 2). Either raise the window for "
            "now or implement the LLM-summarization pass."
        )
