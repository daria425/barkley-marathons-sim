"""Sliding-window history for brain prompts, per CLAUDE.md's Memory and persistence section.

Each brain call gets the last N Observation/Decision pairs verbatim, plus a running summary of
anything older. Per ADR-0008, compaction of aged-out turns is deterministic and code-based (a
template over extracted facts), not an LLM call — this module owns both the sliding-window
replay and the compaction, and both are pure/unit-testable.
"""

from collections import Counter
from dataclasses import dataclass

from models import Decision, Observation

# Single source of truth for the window size, not overridden per-caller. A tuning constant,
# not a documented spec — pick whatever value exercises compaction usefully for a given run.
SLIDING_WINDOW_N = 20

# How many newly-aged-out turns get folded into ONE summary segment at a time. Independent of
# SLIDING_WINDOW_N on purpose: N is "how much recent detail the LLM sees verbatim", this is
# "how coarse the compacted history gets" — a long race (60h/14,400 ticks) needs this decoupled
# from N or the summary grows by one line per tick for the entire race (see memory_example.md
# at the repo root for what that looked like before this was added). Turns that have aged out
# of the window but haven't yet reached a full batch are simply not in the prompt yet — a
# bounded blind spot of at most BATCH_SIZE-1 turns (a few sim-minutes at TICK_DT_MIN=0.25),
# negligible against a 60h race.
COMPACT_BATCH_SIZE = 20

# Mirror physiology.describe_feel's exact strings (sim/physiology.py) so segment extraction can
# rank severity. Not imported directly — Observation.feel is a free-text field (hallucinations
# will inject other strings later per ADR-0001), so this module keeps its own recognized
# vocabulary rather than coupling to physiology's internals.
_COLLAPSED_FEEL = "collapsed, body won't listen anymore"
_BONKING_FEEL = "bonking"
_FEEL_SEVERITY = {"feeling good": 0, "legs heavy": 1, _BONKING_FEEL: 2, _COLLAPSED_FEEL: 3}

# Prose for non-book events, shared between format_observation (in-the-moment, present tense)
# and render_segment (retrospective, past tense) — found_book is handled separately in both
# since books_found_delta already covers it in the summary.
_EVENT_PROMPT_LINES = {
    "tripped_and_fell": "You just tripped and fell hard on the trail!",
    "stepped_in_puddle": "You just stepped ankle-deep into a puddle.",
    "briar_scratch": "A thicket of briars just tore into your arm.",
    "spooked_by_wildlife": "Something rustled in the dark and spooked you badly.",
    "dropped_water_bottle": "You just fumbled and dropped your water bottle.",
}
_EVENT_SUMMARY_PHRASES = {
    "tripped_and_fell": "tripped and fell",
    "stepped_in_puddle": "stepped in a puddle",
    "briar_scratch": "got torn up by briars",
    "spooked_by_wildlife": "got spooked by wildlife",
    "dropped_water_bottle": "dropped a water bottle",
}


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
    # Non-book event counts in this segment (e.g. {"tripped_and_fell": 2}) — found_book is
    # excluded since books_found_delta already captures it. Otherwise these vanish silently
    # once their turn ages out of the sliding window.
    event_counts: dict[str, int]


_Turn = tuple[Observation, Decision]


def _first_matching(turns: list[_Turn], predicate) -> _Turn | None:
    for obs, decision in turns:
        if predicate(obs, decision):
            return obs, decision
    return None


def _first_book_found_turn(turns: list[_Turn]) -> _Turn | None:
    prev_books = turns[0][0].books_found
    for obs, decision in turns[1:]:
        if obs.books_found > prev_books:
            return obs, decision
        prev_books = obs.books_found
    return None


def _pick_highlight_turn(turns: list[_Turn]) -> _Turn:
    """The most narratively "eventful" turn in the segment, in priority order: seriously
    considering quitting beats collapsing beats bonking beats finding a book beats another
    special event (trip/puddle/etc.) beats nothing happening (falls back to the most recent
    turn)."""
    candidates = (
        lambda: _first_matching(turns, lambda o, d: d.quit),
        lambda: _first_matching(turns, lambda o, d: o.feel == _COLLAPSED_FEEL),
        lambda: _first_matching(turns, lambda o, d: o.feel == _BONKING_FEEL),
        lambda: _first_book_found_turn(turns),
        lambda: _first_matching(turns, lambda o, d: o.event not in (None, "found_book")),
    )
    for find in candidates:
        match = find()
        if match is not None:
            return match
    return turns[-1]


def extract_segment_facts(turns: list[tuple[Observation, Decision]]) -> SegmentFacts:
    """Pure extraction from a non-empty, oldest-first list of turns being folded into the
    summary this compaction cycle."""
    feels = [obs.feel for obs, _ in turns]
    _, highlight_decision = _pick_highlight_turn(turns)
    event_counts = Counter(
        obs.event for obs, _ in turns if obs.event is not None and obs.event != "found_book"
    )
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
        event_counts=dict(event_counts),
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
    events_phrase = ""
    if facts.event_counts:
        parts = [
            _EVENT_SUMMARY_PHRASES.get(name, name) + (f" x{count}" if count > 1 else "")
            for name, count in facts.event_counts.items()
        ]
        events_phrase = " Also: " + ", ".join(parts) + "."

    return (
        f"From {facts.start_clock} to {facts.end_clock} (loop {facts.loop}): "
        f"{books_phrase}, {feel_phrase}, {food_phrase}.{quit_phrase}{events_phrase} "
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
        f"Distance to trail: {obs.dist_to_trail_km:.2f}km.",
        f"Terrain: {obs.terrain}. Weather: {obs.weather}.",
    ]
    if obs.event == "found_book":
        lines.append(f"You just found a book at {obs.gps_guess}!")
    elif obs.event is not None and obs.event in _EVENT_PROMPT_LINES:
        lines.append(_EVENT_PROMPT_LINES[obs.event])
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
    folded_count: int,
    n: int = SLIDING_WINDOW_N,
    batch_size: int = COMPACT_BATCH_SIZE,
) -> tuple[str, list[tuple[Observation, Decision]], int]:
    """ADR-0008's compaction trigger, batched (see COMPACT_BATCH_SIZE's docstring on why).
    `all_turns` is the FULL history for this runner, oldest-first (db.get_all_turns, not
    db.get_recent_turns). `folded_count` is how many of the oldest turns are already folded
    into `summary` — the caller's high-water mark, since this function only ever sees a
    snapshot and can't infer it from `summary` text.

    Returns (new_summary, remaining_window, new_folded_count). remaining_window is always
    exactly the last `n` turns, to keep replaying verbatim. Turns between `folded_count` and
    `len(all_turns) - n` are "pending": aged out of the verbatim window but not yet folded,
    because fewer than `batch_size` of them have piled up — nothing happens to them until
    enough accumulate, at which point they're folded into ONE segment together (not one
    segment per turn, which is what made the unbatched version grow by a full line every tick).

    Pure and deterministic given the same inputs — unlike the originally-planned LLM call, this
    is unit-testable without hitting the Anthropic API (ADR-0008)."""
    if len(all_turns) <= n:
        return summary, list(all_turns), folded_count
    fold_upto = len(all_turns) - n
    remaining = all_turns[fold_upto:]
    pending = fold_upto - folded_count
    if pending < batch_size:
        return summary, remaining, folded_count
    aged_out = all_turns[folded_count:fold_upto]
    segment_text = compact_segment(aged_out)
    new_summary = f"{summary}\n{segment_text}" if summary else segment_text
    return new_summary, remaining, fold_upto
