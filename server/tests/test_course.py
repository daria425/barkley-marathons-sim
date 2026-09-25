"""Unit tests for sim/course.py (ADR-0010): free 2D movement, book proximity, loop
completion, and believed-position noise. All pure/deterministic except believed_position,
which is exercised with a seeded rng like the rest of the sim.
"""

import math
from random import Random

from sim import course

COURSE = course.load_course()


def test_load_course_produces_a_real_resampled_loop_with_books():
    assert COURSE.total_km > 0
    assert len(COURSE.points) > 1
    assert len(COURSE.books) == course.N_BOOKS
    # book indices are unique and in range
    assert {b.index for b in COURSE.books} == set(range(course.N_BOOKS))


def test_advance_position_moves_roughly_the_requested_distance_and_bearing():
    start = course.start_coords(COURSE)
    moved = course.advance_position(start, bearing_deg=90.0, distance_km=1.0)
    dist = course.haversine(start, moved, unit=course.Unit.KILOMETERS)
    assert math.isclose(dist, 1.0, rel_tol=1e-3)
    # moving east should increase longitude and barely change latitude
    assert moved[1] > start[1]
    assert math.isclose(moved[0], start[0], abs_tol=1e-3)


def test_advance_position_is_a_noop_for_zero_or_negative_distance():
    start = course.start_coords(COURSE)
    assert course.advance_position(start, 45.0, 0.0) == start
    assert course.advance_position(start, 45.0, -1.0) == start


def test_terrain_and_grade_are_generic_off_the_trail():
    far_away = (course.start_coords(COURSE)[0] + 1.0, course.start_coords(COURSE)[1] + 1.0)
    assert course.terrain_at(COURSE, far_away) == course.OFF_TRAIL_TERRAIN
    assert course.grade_pct_at(COURSE, far_away) == 0.0


def test_terrain_on_trail_is_one_of_the_labeled_buckets():
    on_trail = (COURSE.points[10].lat, COURSE.points[10].lon)
    assert course.terrain_at(COURSE, on_trail) in course.TERRAIN_LABELS


def test_dist_to_trail_km_is_near_zero_on_trail():
    on_trail = (COURSE.points[10].lat, COURSE.points[10].lon)
    assert course.dist_to_trail_km(COURSE, on_trail) < 1e-6


def test_dist_to_trail_km_grows_with_distance_unlike_terrain_text():
    """The bug this field fixes: terrain_at reads identically far or a little off-trail
    (see test_terrain_and_grade_are_generic_off_the_trail) — dist_to_trail_km must not,
    since it's the only signal a bearing choice can actually move. Uses big lat/lon offsets
    (like that test) so both points are unambiguously off-trail, not just past the threshold
    by chance depending on where the loop happens to curve back nearby."""
    start_lat, start_lon = course.start_coords(COURSE)
    near = (start_lat + 0.01, start_lon + 0.01)  # ~1km away
    far = (start_lat + 0.1, start_lon + 0.1)  # ~11km away
    near_dist = course.dist_to_trail_km(COURSE, near)
    far_dist = course.dist_to_trail_km(COURSE, far)
    assert course.TRAIL_PROXIMITY_KM < near_dist < far_dist
    # both read as the same generic off-trail terrain despite the very different distances
    near_terrain = course.terrain_at(COURSE, near)
    far_terrain = course.terrain_at(COURSE, far)
    assert near_terrain == far_terrain == course.OFF_TRAIL_TERRAIN


def test_books_found_this_tick_is_monotonic_and_proximity_triggered():
    book = COURSE.books[0]
    found, has_found_new = course.books_found_this_tick(COURSE, (book.lat, book.lon), frozenset())
    assert book.index in found
    assert has_found_new

    far_away = (COURSE.points[0].lat + 1.0, COURSE.points[0].lon + 1.0)
    still_found, has_found_new_again = course.books_found_this_tick(COURSE, far_away, found)
    assert found <= still_found  # never loses a previously found book
    assert not has_found_new_again


def test_loop_not_completed_near_start_before_covering_distance():
    start = course.start_coords(COURSE)
    assert not course.loop_completed(COURSE, start, dist_since_loop_start_km=0.0)


def test_loop_completed_once_distance_covered_and_back_near_start():
    start = course.start_coords(COURSE)
    halfway = COURSE.total_km * course.LOOP_COMPLETE_MIN_FRACTION
    assert course.loop_completed(COURSE, start, dist_since_loop_start_km=halfway)


def test_detect_special_event_never_fires_on_ungated_terrain_with_zero_chance():
    """With every gated chance zeroed via monkeypatched rng (always returns 1.0, above any
    threshold), only the ungated dropped_water_bottle check could ever fire — and it won't
    either, since 1.0 is never < any probability. Confirms gating actually gates."""

    class _AlwaysOne:
        def random(self):
            return 1.0

    result = course.detect_special_event(
        terrain="thick briars", grade_pct=0.0, is_daylight=True, rng=_AlwaysOne()
    )
    assert result is None


def test_detect_special_event_fires_on_qualifying_terrain_with_favorable_rng():
    class _AlwaysZero:
        def random(self):
            return 0.0

    assert (
        course.detect_special_event("steep scree", 0.0, True, rng=_AlwaysZero())
        == "tripped_and_fell"
    )
    assert (
        course.detect_special_event("creek crossing", 0.0, True, rng=_AlwaysZero())
        == "stepped_in_puddle"
    )
    assert (
        course.detect_special_event("thick briars", 0.0, True, rng=_AlwaysZero()) == "briar_scratch"
    )
    assert (
        course.detect_special_event("gravel road, gentle climb", 0.0, False, rng=_AlwaysZero())
        == "spooked_by_wildlife"
    )


def test_detect_special_event_falls_through_to_bottle_drop_when_ungated_only():
    class _AlwaysZero:
        def random(self):
            return 0.0

    # daylight + terrain that qualifies for nothing gated — only the ungated check can fire
    assert (
        course.detect_special_event("gravel road, gentle climb", 0.0, True, rng=_AlwaysZero())
        == "dropped_water_bottle"
    )


def test_detect_special_event_steep_grade_counts_as_trip_prone_even_off_labeled_terrain():
    class _AlwaysZero:
        def random(self):
            return 0.0

    result = course.detect_special_event(
        "gravel road, gentle climb", grade_pct=20.0, is_daylight=True, rng=_AlwaysZero()
    )
    assert result == "tripped_and_fell"


def test_detect_special_event_is_deterministic_for_a_given_rng_state():
    rng_a = Random(5)
    rng_b = Random(5)
    results = [course.detect_special_event("thick briars", 0.0, True, rng_a) for _ in range(50)]
    results_again = [
        course.detect_special_event("thick briars", 0.0, True, rng_b) for _ in range(50)
    ]
    assert results == results_again


def test_believed_position_noise_grows_with_fog_and_night():
    rng_clear_day = Random(1)
    rng_fog_night = Random(1)
    true_pos = course.start_coords(COURSE)

    clear_day = course.believed_position(
        true_pos, fog_pct=0.0, is_daylight=True, elapsed_min=0.0, rng=rng_clear_day
    )
    fog_night = course.believed_position(
        true_pos, fog_pct=100.0, is_daylight=False, elapsed_min=0.0, rng=rng_fog_night
    )

    dist_clear = course.haversine(true_pos, clear_day, unit=course.Unit.KILOMETERS)
    dist_fog = course.haversine(true_pos, fog_night, unit=course.Unit.KILOMETERS)
    assert dist_fog > dist_clear
