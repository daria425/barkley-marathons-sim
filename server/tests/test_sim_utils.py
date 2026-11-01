from sim.sim_utils import calculate_day, calculate_hour, format_clock_time, whole_minutes


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


def test_whole_minutes_floors_instead_of_banker_rounding():
    # round() gave 26, 26, 26, 27, 28 here: .5 rounds to the nearest even number
    assert [whole_minutes(m) for m in (25.5, 26.0, 26.5, 27.0, 27.5)] == [25, 26, 26, 27, 27]
    assert whole_minutes(26.9999999) == 27  # float drift from summed ticks


def test_clock_advances_one_minute_every_two_half_minute_ticks():
    ticks = [n * 0.5 for n in range(50, 56)]  # 25.0 .. 27.5
    clocks = [format_clock_time(start_hour=6.0, elapsed_min=t) for t in ticks]
    assert clocks == [
        "Day 1, 6:25 AM",
        "Day 1, 6:25 AM",
        "Day 1, 6:26 AM",
        "Day 1, 6:26 AM",
        "Day 1, 6:27 AM",
        "Day 1, 6:27 AM",
    ]


def test_clock_rolls_over_midnight_without_a_60_minute_reading():
    assert format_clock_time(start_hour=23.0, elapsed_min=59.5) == "Day 1, 11:59 PM"
    assert format_clock_time(start_hour=23.0, elapsed_min=60) == "Day 2, 12:00 AM"
