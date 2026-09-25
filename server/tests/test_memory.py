"""Unit tests for ADR-0008's deterministic, code-based compaction.

Unlike the originally-planned LLM summary, this is fully unit-testable — no API calls, no
eyeballing prose. That testability is the entire point of ADR-0008, so these tests exercise it
directly: fact extraction, highlight-turn priority, and the compact_if_needed trigger/window
math.
"""

from agents.memory import (
    SLIDING_WINDOW_N,
    compact_if_needed,
    extract_segment_facts,
    format_observation,
    render_segment,
)
from models import Decision, Observation


def make_turn(
    elapsed_min: int,
    feel: str = "feeling good",
    books_found: int = 0,
    loop: int = 1,
    eat: bool = False,
    drink: bool = False,
    rest_min: int = 0,
    quit: bool = False,
    monologue: str = "",
    event: str | None = None,
) -> tuple[Observation, Decision]:
    obs = Observation(
        elapsed_min=elapsed_min,
        clock_time=f"Day 1, turn {elapsed_min}",
        hr=140,
        pace_min_per_km=8.0,
        cadence=170,
        feel=feel,
        last_ate_min_ago=0,
        bearing_deg=0.0,
        gps_guess=(0.0, 0.0),
        dist_to_trail_km=0.0,
        terrain="gravel road",
        weather="clear",
        books_found=books_found,
        loop=loop,
        hallucination=None,
        event=event,
    )
    decision = Decision(
        effort=5,
        eat=eat,
        drink=drink,
        bearing_deg=0.0,
        rest_min=rest_min,
        quit=quit,
        monologue=monologue,
    )
    return obs, decision


def test_extract_segment_facts_counts_books_food_and_rest():
    turns = [
        make_turn(0, books_found=0, eat=True),
        make_turn(1, books_found=1, drink=True),
        make_turn(2, books_found=1, rest_min=10),
    ]
    facts = extract_segment_facts(turns)
    assert facts.books_found_delta == 1
    assert facts.ate_count == 1
    assert facts.drank_count == 1
    assert facts.total_rest_min == 10
    assert facts.loop == turns[-1][0].loop
    assert facts.start_clock == turns[0][0].clock_time
    assert facts.end_clock == turns[-1][0].clock_time


def test_worst_feel_prioritizes_collapse_over_bonking_over_heavy_over_good():
    turns = [
        make_turn(0, feel="feeling good"),
        make_turn(1, feel="legs heavy"),
        make_turn(2, feel="bonking"),
        make_turn(3, feel="collapsed, body won't listen anymore"),
    ]
    assert extract_segment_facts(turns).worst_feel == "collapsed, body won't listen anymore"


def test_worst_feel_ignores_order():
    turns = [
        make_turn(0, feel="collapsed, body won't listen anymore"),
        make_turn(1, feel="feeling good"),
    ]
    assert extract_segment_facts(turns).worst_feel == "collapsed, body won't listen anymore"


def test_quit_considered_true_even_if_it_didnt_stick():
    turns = [make_turn(0, quit=True), make_turn(1, quit=False)]
    assert extract_segment_facts(turns).quit_considered is True


def test_highlight_prefers_quit_over_everything():
    turns = [
        make_turn(0, books_found=0, monologue="found a book!"),
        make_turn(1, books_found=1, monologue="found a book!"),
        make_turn(2, quit=True, monologue="i'm done"),
        make_turn(3, feel="bonking", monologue="bonking hard"),
    ]
    assert extract_segment_facts(turns).highlight_monologue == "i'm done"


def test_highlight_prefers_collapse_over_bonk_and_books():
    turns = [
        make_turn(0, books_found=0),
        make_turn(1, books_found=1, monologue="found a book!"),
        make_turn(2, feel="bonking", monologue="bonking hard"),
        make_turn(3, feel="collapsed, body won't listen anymore", monologue="can't go on"),
    ]
    assert extract_segment_facts(turns).highlight_monologue == "can't go on"


def test_highlight_prefers_bonk_over_book():
    turns = [
        make_turn(0, books_found=0),
        make_turn(1, books_found=1, monologue="found a book!"),
        make_turn(2, feel="bonking", monologue="bonking hard"),
    ]
    assert extract_segment_facts(turns).highlight_monologue == "bonking hard"


def test_highlight_falls_back_to_last_turn_when_nothing_eventful():
    turns = [make_turn(0, monologue="fine"), make_turn(1, monologue="still fine")]
    assert extract_segment_facts(turns).highlight_monologue == "still fine"


def test_event_counts_tallies_non_book_events_and_excludes_found_book():
    turns = [
        make_turn(0, event="found_book"),
        make_turn(1, event="tripped_and_fell"),
        make_turn(2, event="tripped_and_fell"),
        make_turn(3, event="stepped_in_puddle"),
        make_turn(4, event=None),
    ]
    facts = extract_segment_facts(turns)
    assert facts.event_counts == {"tripped_and_fell": 2, "stepped_in_puddle": 1}


def test_highlight_prefers_special_event_over_fallback():
    turns = [
        make_turn(0, monologue="fine"),
        make_turn(1, event="briar_scratch", monologue="ouch, briars"),
        make_turn(2, monologue="still fine"),
    ]
    assert extract_segment_facts(turns).highlight_monologue == "ouch, briars"


def test_highlight_prefers_book_over_special_event():
    turns = [
        make_turn(0, books_found=0),
        make_turn(1, books_found=1, monologue="found a book!"),
        make_turn(2, event="briar_scratch", monologue="ouch, briars"),
    ]
    assert extract_segment_facts(turns).highlight_monologue == "found a book!"


def test_render_segment_mentions_special_events_with_counts():
    turns = [
        make_turn(0, event="tripped_and_fell"),
        make_turn(1, event="tripped_and_fell"),
        make_turn(2, event="stepped_in_puddle"),
    ]
    text = render_segment(extract_segment_facts(turns))
    assert "tripped and fell x2" in text
    assert "stepped in a puddle" in text


def test_render_segment_has_no_events_clause_when_nothing_happened():
    turns = [make_turn(0), make_turn(1)]
    text = render_segment(extract_segment_facts(turns))
    assert "Also:" not in text


def test_format_observation_includes_special_event_line():
    obs, _ = make_turn(0, event="stepped_in_puddle")
    assert "puddle" in format_observation(obs)


def test_format_observation_omits_event_line_when_none():
    obs, _ = make_turn(0, event=None)
    text = format_observation(obs)
    assert "puddle" not in text
    assert "tripped" not in text
    assert "just found a book" not in text


def test_compact_if_needed_leaves_short_history_untouched():
    turns = [make_turn(i) for i in range(SLIDING_WINDOW_N)]
    summary, remaining, folded_count = compact_if_needed("", turns, folded_count=0)
    assert summary == ""
    assert remaining == turns
    assert folded_count == 0


def test_compact_if_needed_folds_oldest_and_keeps_last_n():
    n = 5
    turns = [make_turn(i) for i in range(n + 3)]
    summary, remaining, folded_count = compact_if_needed(
        "", turns, folded_count=0, n=n, batch_size=1
    )
    assert remaining == turns[3:]
    assert summary != ""
    assert folded_count == 3


def test_compact_if_needed_appends_to_existing_summary():
    n = 3
    turns = [make_turn(i) for i in range(n + 2)]
    summary, _, _ = compact_if_needed(
        "earlier summary text", turns, folded_count=0, n=n, batch_size=1
    )
    assert summary.startswith("earlier summary text\n")


def test_compact_if_needed_is_deterministic():
    n = 4
    turns = [make_turn(i, feel="bonking" if i == 1 else "feeling good") for i in range(n + 2)]
    result_a = compact_if_needed("prior", turns, folded_count=0, n=n, batch_size=1)
    result_b = compact_if_needed("prior", turns, folded_count=0, n=n, batch_size=1)
    assert result_a == result_b


def test_compact_if_needed_holds_pending_turns_below_batch_size():
    """Fewer than batch_size turns aged out of the window: nothing gets folded yet — turns sit
    pending rather than each spawning its own summary line (the pre-fix behavior)."""
    n = 5
    turns = [make_turn(i) for i in range(n + 2)]  # only 2 turns pending, batch_size defaults 20
    summary, remaining, folded_count = compact_if_needed("", turns, folded_count=0, n=n)
    assert summary == ""
    assert folded_count == 0
    assert remaining == turns[-n:]


def test_compact_if_needed_folds_one_segment_per_batch_not_per_tick():
    """Regression test for the original bug: replaying loop.py's call-every-tick pattern across
    many ticks should produce one summary line per full batch, not one line per tick."""
    n = 5
    batch_size = 4
    summary = ""
    folded_count = 0
    all_turns: list[tuple] = []
    for i in range(30):
        all_turns.append(make_turn(i))
        summary, _, folded_count = compact_if_needed(
            summary, all_turns, folded_count, n=n, batch_size=batch_size
        )
    pending_after_last_batch = (len(all_turns) - n - folded_count) % batch_size
    expected_batches = (len(all_turns) - n) // batch_size
    assert folded_count == expected_batches * batch_size
    assert summary.count("\n") == expected_batches - 1
    assert pending_after_last_batch < batch_size
