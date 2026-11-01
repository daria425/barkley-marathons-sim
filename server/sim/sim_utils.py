"Shared utils so that we dont duplicate"

import math

# tolerance so float drift (e.g. 26.999999 from summed tick sizes) still counts as minute 27
_MINUTE_EPSILON = 1e-6


def whole_minutes(minutes: float) -> int:
    """Floor to the whole minute. Not round(): Python rounds .5 to the nearest even number, so
    with 30s ticks round() showed minute 26 for three ticks (25.5, 26.0, 26.5) and minute 27 for
    one, and the clock went 6:26, 6:26, 6:26, 6:27, 6:28. Flooring reads like a stopwatch: every
    minute shows for the same number of ticks and never runs ahead of real elapsed time."""
    return math.floor(minutes + _MINUTE_EPSILON)


def calculate_hour(start_hour: float, elapsed_min: float) -> float:
    hour = (start_hour + elapsed_min / 60) % 24
    return hour


def calculate_day(start_hour: float, elapsed_min: float) -> int:
    """Race day number, starting at 1 — Barkley's start horn can blow any time
    midnight-noon (CLAUDE.md), so a run that starts at e.g. 22:00 rolls into day 2 fast."""
    total_hours = start_hour + elapsed_min / 60
    return int(total_hours // 24) + 1


def format_clock_time(start_hour: float, elapsed_min: float) -> str:
    """Human clock time for the LLM prompt — runners think in "3am on day 2", not
    elapsed-minutes-since-start."""
    day = calculate_day(start_hour, elapsed_min)
    minute_of_day = whole_minutes(start_hour * 60 + elapsed_min) % (24 * 60)
    hh, mm = divmod(minute_of_day, 60)
    period = "AM" if hh < 12 else "PM"
    display_hour = hh % 12 or 12
    return f"Day {day}, {display_hour}:{mm:02d} {period}"


def format_local_time(start_hour: float, elapsed_min: float) -> str:
    """Same race-clock math as format_clock_time, labeled as Frozen Head State Park's real
    timezone (Tennessee is US Eastern) for FrozenHeadStatePark.local_time — a frontend-facing
    field, not the LLM prompt's clock_time. Deliberately not anchored to a real datetime.now():
    sim/*.py is pure/deterministic by design (ADR-0002, ADR-0003), and the race has no real
    calendar date, only a race-day number — this only makes the existing hour-of-day honest
    about which real timezone it corresponds to."""
    return f"{format_clock_time(start_hour, elapsed_min)} ET"
