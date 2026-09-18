"Shared utils so that we dont duplicate"


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
    hour = calculate_hour(start_hour, elapsed_min)
    hh, mm = int(hour), round((hour % 1) * 60)
    if mm == 60:
        hh, mm = (hh + 1) % 24, 0
    period = "AM" if hh < 12 else "PM"
    display_hour = hh % 12 or 12
    return f"Day {day}, {display_hour}:{mm:02d} {period}"
