from sim.sim_utils import calculate_day, calculate_hour, format_clock_time


def test_calculate_hour_wraps_at_24():
    assert calculate_hour(start_hour=22.0, elapsed_min=180) == 1.0


def test_calculate_day_starts_at_one():
    assert calculate_day(start_hour=6.0, elapsed_min=0) == 1


def test_calculate_day_rolls_over_past_midnight():
    # starts 10pm, 3 hours in -> day 2, 1am
    assert calculate_day(start_hour=22.0, elapsed_min=180) == 2


def test_format_clock_time_am_pm():
    assert format_clock_time(start_hour=6.0, elapsed_min=0) == "Day 1, 6:00 AM"
    assert format_clock_time(start_hour=22.0, elapsed_min=180) == "Day 2, 1:00 AM"
    assert format_clock_time(start_hour=0.0, elapsed_min=0) == "Day 1, 12:00 AM"
    assert format_clock_time(start_hour=12.0, elapsed_min=0) == "Day 1, 12:00 PM"
