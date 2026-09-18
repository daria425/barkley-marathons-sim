"""Sliding-window history for brain prompts, per CLAUDE.md's Memory and persistence section.

Each brain call gets the last N Observation/Decision pairs verbatim, plus a running summary of
anything older. Per ADR-0008, compaction of aged-out turns is deterministic and code-based (a
template over extracted facts), not an LLM call — this module owns both the sliding-window
replay and the compaction, and both are pure/unit-testable.
"""

from dataclasses import dataclass

from models import Decision, Observation

# CLAUDE.md's real-race spec says N=10; lowered further to 5 for now so ADR-0008's compaction
# path actually exercises within the short dev-speed smoke test — single source of truth for
# the window size, not overridden per-caller. Revisit before the real run (ADR-0005).
SLIDING_WINDOW_N = 5

# Mirror physiology.describe_feel's exact strings (sim/physiology.py) so segment extraction can
# rank severity. Not imported directly — Observation.feel is a free-text field (hallucinations
# will inject other strings later per ADR-0001), so this module keeps its own recognized
# vocabulary rather than coupling to physiology's internals.
_COLLAPSED_FEEL = "collapsed, body won't listen anymore"
_BONKING_FEEL = "bonking"
_FEEL_SEVERITY = {"feeling good": 0, "legs heavy": 1, _BONKING_FEEL: 2, _COLLAPSED_FEEL: 3}


@dataclass(frozen=True)
class SegmentFacts:
    """Extracted, structured facts about a run of aged-out turns — the input to
    render_segment(). Kept separate from rendering so degradation (ADR-0001's hallucination
    mechanic: dropping/misattributing facts as sleep debt rises) has a clean seam to hook into
    later, without touching the extraction or template logic."""

    start_clock: str
    end_clock: str
    loop: int
    books_found_delta: int
    worst_feel: str
    ate_count: int
    drank_count: int
    total_rest_min: int
    quit_considered: bool
    highlight_monologue: str


def _pick_highlight_turn(
    turns: list[tuple[Observation, Decision]],
) -> tuple[Observation, Decision]:
    """The most narratively "eventful" turn in the segment, in priority order: seriously
    considering quitting beats collapsing beats bonking beats finding a book beats nothing
    happening (falls back to the most recent turn)."""
    for obs, decision in turns:
        if decision.quit:
            return obs, decision
    for obs, decision in turns:
        if obs.feel == _COLLAPSED_FEEL:
            return obs, decision
    for obs, decision in turns:
        if obs.feel == _BONKING_FEEL:
            return obs, decision
    prev_books = turns[0][0].books_found
    for obs, decision in turns[1:]:
        if obs.books_found > prev_books:
            return obs, decision
        prev_books = obs.books_found
    return turns[-1]


def extract_segment_facts(turns: list[tuple[Observation, Decision]]) -> SegmentFacts:
    """Pure extraction from a non-empty, oldest-first list of turns being folded into the
    summary this compaction cycle."""
    feels = [obs.feel for obs, _ in turns]
    _, highlight_decision = _pick_highlight_turn(turns)
    return SegmentFacts(
        start_clock=turns[0][0].clock_time,
        end_clock=turns[-1][0].clock_time,
        loop=turns[-1][0].loop,
        books_found_delta=turns[-1][0].books_found - turns[0][0].books_found,
        worst_feel=max(feels, key=lambda f: _FEEL_SEVERITY.get(f, 0)),
        ate_count=sum(1 for _, d in turns if d.eat),
        drank_count=sum(1 for _, d in turns if d.drink),
        total_rest_min=sum(d.rest_min for _, d in turns),
        quit_considered=any(d.quit for _, d in turns),
        highlight_monologue=highlight_decision.monologue,
    )


_FEEL_PHRASES = {
    _COLLAPSED_FEEL: "the body gave out and forced a collapse",
    _BONKING_FEEL: "bonked hard",
    "legs heavy": "legs got heavy",
    "feeling good": "felt strong throughout",
}


def render_segment(facts: SegmentFacts) -> str:
    """Deterministic template rendering — see SegmentFacts' docstring on why this stays
    separate from extraction."""
    books_phrase = (
        f"found {facts.books_found_delta} book(s)" if facts.books_found_delta else "found no books"
    )
    feel_phrase = _FEEL_PHRASES.get(facts.worst_feel, facts.worst_feel)
    food_phrase = f"ate {facts.ate_count}x and drank {facts.drank_count}x"
    if facts.total_rest_min:
        food_phrase += f", rested {facts.total_rest_min:.0f}m"
    quit_phrase = " Seriously considered quitting." if facts.quit_considered else ""

    return (
        f"From {facts.start_clock} to {facts.end_clock} (loop {facts.loop}): "
        f"{books_phrase}, {feel_phrase}, {food_phrase}.{quit_phrase} "
        f'"{facts.highlight_monologue}"'
    )


def compact_segment(turns: list[tuple[Observation, Decision]]) -> str:
    return render_segment(extract_segment_facts(turns))


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


def compact_if_needed(
    summary: str,
    all_turns: list[tuple[Observation, Decision]],
    n: int = SLIDING_WINDOW_N,
) -> tuple[str, list[tuple[Observation, Decision]]]:
    """ADR-0008's compaction trigger: if `all_turns` (the FULL history for this runner,
    oldest-first — db.get_all_turns, not db.get_recent_turns) has more than `n` entries, fold
    the oldest `len(all_turns) - n` into `summary` as one segment. Returns
    (new_summary, remaining_window) where remaining_window is exactly the last `n` turns to
    keep replaying verbatim.

    Pure and deterministic given the same inputs — unlike the originally-planned LLM call, this
    is unit-testable without hitting the Anthropic API (ADR-0008)."""
    if len(all_turns) <= n:
        return summary, list(all_turns)
    split = len(all_turns) - n
    aged_out, remaining = all_turns[:split], all_turns[split:]
    segment_text = compact_segment(aged_out)
    new_summary = f"{summary}\n{segment_text}" if summary else segment_text
    return new_summary, remaining
