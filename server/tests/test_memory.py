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
        terrain="gravel road",
        weather="clear",
        books_found=books_found,
        loop=loop,
        hallucination=None,
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


def test_compact_if_needed_leaves_short_history_untouched():
    turns = [make_turn(i) for i in range(SLIDING_WINDOW_N)]
    summary, remaining = compact_if_needed("", turns)
    assert summary == ""
    assert remaining == turns


def test_compact_if_needed_folds_oldest_and_keeps_last_n():
    n = 5
    turns = [make_turn(i) for i in range(n + 3)]
    summary, remaining = compact_if_needed("", turns, n=n)
    assert remaining == turns[3:]
    assert summary != ""


def test_compact_if_needed_appends_to_existing_summary():
    n = 3
    turns = [make_turn(i) for i in range(n + 2)]
    summary, _ = compact_if_needed("earlier summary text", turns, n=n)
    assert summary.startswith("earlier summary text\n")


def test_compact_if_needed_is_deterministic():
    n = 4
    turns = [make_turn(i, feel="bonking" if i == 1 else "feeling good") for i in range(n + 2)]
    result_a = compact_if_needed("prior", turns, n=n)
    result_b = compact_if_needed("prior", turns, n=n)
    assert result_a == result_b
