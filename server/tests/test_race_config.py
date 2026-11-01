"""Unit tests for sim/race_config.py (ADR-0024): the fixed weather cycle, the event and
hallucination schedules, loading/validation, and the per-tick GPS-noise rng. Plus the
found_book deferral in sim/loop.py, which is what keeps every scheduled event delivered."""

from dataclasses import replace

import pytest
from pydantic import ValidationError
from race_config_helpers import make_race_config

from sim import race_config
from sim.frozen_head_state_park import compute_is_daylight
from sim.loop import _next_scheduled_event, build_initial_state


def test_weather_cycles_clear_fog_rain_every_six_hours():
    config = make_race_config()
    expected = {0: "clear", 119.5: "clear", 120: "fog", 239.5: "fog", 240: "rain", 359.5: "rain"}
    for minute, weather in expected.items():
        assert race_config.weather_at(config, minute) == weather
        assert race_config.weather_at(config, minute + 360 * 9) == weather  # loops all race


def test_events_due_uses_a_half_open_window_so_each_fires_exactly_once():
    config = make_race_config(events=[(40.0, "spooked_by_wildlife"), (40.0, "briar_scratch")])
    ticks = [i * 0.5 for i in range(200)]
    fired = [
        e
        for prev, now in zip(ticks, ticks[1:], strict=False)
        for e in race_config.events_due(config, prev, now)
    ]
    assert fired == ["spooked_by_wildlife", "briar_scratch"]
    assert race_config.events_due(config, 39.5, 40.0) == fired
    assert race_config.events_due(config, 40.0, 40.5) == []


def test_hallucination_due_fires_on_its_tick_only():
    config = make_race_config(hallucinations=[(2400.0, "The trees are whispering your name.")])
    assert race_config.hallucination_due(config, 2399.5, 2400.0) == (
        "The trees are whispering your name."
    )
    assert race_config.hallucination_due(config, 2400.0, 2400.5) is None


def test_gps_rng_is_the_same_stream_for_the_same_seed_and_minute():
    a = race_config.gps_rng(1, 42.5)
    b = race_config.gps_rng(1, 42.5)
    assert [a.random() for _ in range(3)] == [b.random() for _ in range(3)]
    assert race_config.gps_rng(1, 42.5).random() != race_config.gps_rng(1, 43.0).random()
    assert race_config.gps_rng(1, 42.5).random() != race_config.gps_rng(2, 42.5).random()


def test_config_hash_changes_when_any_condition_changes():
    base = make_race_config()
    assert race_config.config_hash(base) == race_config.config_hash(make_race_config())
    assert race_config.config_hash(base) != race_config.config_hash(
        make_race_config(events=[(10.0, "briar_scratch")])
    )


def test_found_book_cannot_be_scheduled():
    with pytest.raises(ValidationError):
        make_race_config(events=[(10.0, "found_book")])


def test_unknown_weather_is_rejected():
    with pytest.raises(ValidationError):
        race_config.WeatherPhase(condition="sleet", duration_min=60)


def test_event_at_minute_zero_is_rejected():
    """The first tick's window is (0, 0.5], so an event at 0 could never fire."""
    with pytest.raises(ValidationError):
        make_race_config(events=[(0.0, "briar_scratch")])


@pytest.mark.parametrize("name", ["../secrets", "study-01.yaml", "", "a/b"])
def test_load_race_config_rejects_names_that_arent_a_bare_file_stem(name):
    with pytest.raises(ValueError):
        race_config.load_race_config(name)


def test_load_race_config_raises_for_a_missing_file():
    with pytest.raises(FileNotFoundError):
        race_config.load_race_config("no-such-race")


def test_study_01_loads_and_its_schedule_fits_its_own_conditions():
    """Guards the hand-placed draft against later edits: wildlife only at night, puddles only in
    rain, trips only in fog/rain (see the comments in races/study-01.yaml)."""
    config = race_config.load_race_config("study-01")
    assert config.start_hour == 6.0
    for scheduled in config.events:
        minute = scheduled.at_elapsed_min
        weather = race_config.weather_at(config, minute)
        if scheduled.event == "spooked_by_wildlife":
            assert not compute_is_daylight(minute, config.start_hour), minute
        if scheduled.event == "stepped_in_puddle":
            assert weather == "rain", minute
        if scheduled.event == "tripped_and_fell":
            assert weather in ("fog", "rain"), minute
    assert all(h.at_elapsed_min >= 40 * 60 for h in config.hallucinations)


def test_scheduled_event_waits_out_a_found_book_tick():
    state = build_initial_state(make_race_config(events=[(1.0, "briar_scratch")]))
    state.physio = replace(state.physio, elapsed_min=1.0)

    assert _next_scheduled_event(state, 0.5, has_found_new_book=True) is None
    assert state.pending_events == ("briar_scratch",)

    state.physio = replace(state.physio, elapsed_min=1.5)
    assert _next_scheduled_event(state, 1.0, has_found_new_book=False) == "briar_scratch"
    assert state.pending_events == ()


def test_pending_events_go_out_one_per_tick_in_order():
    config = make_race_config(events=[(1.0, "briar_scratch"), (1.0, "tripped_and_fell")])
    state = build_initial_state(config)
    state.physio = replace(state.physio, elapsed_min=1.0)
    assert _next_scheduled_event(state, 0.5, has_found_new_book=False) == "briar_scratch"
    state.physio = replace(state.physio, elapsed_min=1.5)
    assert _next_scheduled_event(state, 1.0, has_found_new_book=False) == "tripped_and_fell"
    assert state.pending_events == ()


def test_post_run_requires_a_known_race(monkeypatch):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setattr(main, "RACE_ADMIN_TOKEN", "secret")
    headers = {"x-admin-token": "secret"}
    with TestClient(main.app) as client:
        assert client.post("/run?speed=1", headers=headers).status_code == 422
        assert client.post("/run?race=no-such-race", headers=headers).status_code == 404
        assert client.post("/run?race=..%2Fsecrets", headers=headers).status_code == 404
