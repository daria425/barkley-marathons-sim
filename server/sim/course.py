"""Course geometry: the GPX loop, synthetic book placements, and the true-vs-believed
position comedy engine (ADR-0010).

Movement is genuinely free 2D: true_pos moves by compass bearing + distance each tick, with
no coupling back to the trail polyline — a bad bearing just walks the runner off trail, no
special-cased "penalty" math needed. The polyline exists only to place books, derive
terrain/grade near the trail, and detect loop completion.

Book "page matches your bib number" (the real Barkley rule) is flavor, not a mechanic this
module models — see ADR-0010. books_found is a plain per-loop proximity counter.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from random import Random

import gpxpy
from haversine import Unit, haversine, inverse_haversine

from sim.sim_constants import (
    BOOK_PROXIMITY_KM,
    BOTTLE_DROP_CHANCE_PER_TICK,
    BRIAR_CHANCE_PER_TICK,
    BRIAR_TERRAIN,
    LOOP_COMPLETE_MIN_FRACTION,
    LOOP_COMPLETE_RADIUS_KM,
    N_BOOKS,
    NOISE_BASE_KM,
    NOISE_FATIGUE_CAP_KM,
    NOISE_FATIGUE_PER_HOUR_KM,
    NOISE_FOG_SCALE_KM,
    NOISE_NIGHT_KM,
    OFF_TRAIL_TERRAIN,
    PUDDLE_CHANCE_PER_TICK,
    PUDDLE_TERRAIN,
    RESAMPLE_INTERVAL_KM,
    TERRAIN_LABELS,
    TRAIL_PROXIMITY_KM,
    TRIP_CHANCE_PER_TICK,
    TRIP_GRADE_PCT_THRESHOLD,
    TRIP_TERRAIN,
    WILDLIFE_CHANCE_PER_TICK,
)

GPX_PATH = Path(__file__).parent.parent / "files" / "Barkley_Challenge_Loop_FKT.gpx"


@dataclass(frozen=True)
class TrailPoint:
    lat: float
    lon: float
    elevation_m: float
    cum_km: float  # cumulative distance along the loop from the start


@dataclass(frozen=True)
class Book:
    index: int
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Course:
    points: tuple[TrailPoint, ...]
    total_km: float
    books: tuple[Book, ...]


def _raw_points() -> list[tuple[float, float, float]]:
    with GPX_PATH.open() as f:
        gpx = gpxpy.parse(f)
    return [(p.latitude, p.longitude, p.elevation or 0.0) for p in gpx.tracks[0].segments[0].points]


def _resample(raw: list[tuple[float, float, float]]) -> list[TrailPoint]:
    points = [TrailPoint(raw[0][0], raw[0][1], raw[0][2], 0.0)]
    cum_km = 0.0
    last = (raw[0][0], raw[0][1])
    for lat, lon, elevation_m in raw[1:]:
        cum_km += haversine(last, (lat, lon), unit=Unit.KILOMETERS)
        last = (lat, lon)
        if cum_km - points[-1].cum_km >= RESAMPLE_INTERVAL_KM:
            points.append(TrailPoint(lat, lon, elevation_m, cum_km))
    return points


def _place_books(points: list[TrailPoint], total_km: float) -> tuple[Book, ...]:
    """Fixed, evenly spaced distances around the loop — deterministic, not rng-placed, so a
    given course always has the same book locations."""
    books = []
    for i in range(N_BOOKS):
        target_km = total_km * (i + 1) / (N_BOOKS + 1)
        nearest = min(points, key=lambda p: abs(p.cum_km - target_km))
        books.append(Book(index=i, name=f"Book {i + 1}", lat=nearest.lat, lon=nearest.lon))
    return tuple(books)


@lru_cache(maxsize=1)
def load_course() -> Course:
    points = _resample(_raw_points())
    total_km = points[-1].cum_km
    return Course(points=tuple(points), total_km=total_km, books=_place_books(points, total_km))


def start_coords(course: Course) -> tuple[float, float]:
    return (course.points[0].lat, course.points[0].lon)


def _nearest_point_idx(course: Course, pos: tuple[float, float]) -> tuple[int, float]:
    """Index of the nearest trail point to `pos`, and the distance to it in km."""
    best_idx, best_dist = 0, math.inf
    for i, p in enumerate(course.points):
        dist = haversine(pos, (p.lat, p.lon), unit=Unit.KILOMETERS)
        if dist < best_dist:
            best_idx, best_dist = i, dist
    return best_idx, best_dist


def terrain_at(course: Course, pos: tuple[float, float]) -> str:
    idx, dist_km = _nearest_point_idx(course, pos)
    if dist_km > TRAIL_PROXIMITY_KM:
        return OFF_TRAIL_TERRAIN
    bucket = int(course.points[idx].cum_km / course.total_km * len(TERRAIN_LABELS))
    return TERRAIN_LABELS[bucket % len(TERRAIN_LABELS)]


def dist_to_trail_km(course: Course, pos: tuple[float, float]) -> float:
    """Raw distance to the nearest trail point, in km — not clamped to
    TRAIL_PROXIMITY_KM's on/off-trail threshold. Unlike terrain_at (a single fixed string for
    ANY off-trail position, however far), this is continuous: it's the only signal in the
    Observation that actually varies with bearing/position once off-trail, so a runner can
    tell a bearing is working from this shrinking turn over turn, not just from terrain text
    that reads identically whether you're 200m or 5km off course."""
    _, dist_km = _nearest_point_idx(course, pos)
    return dist_km


def grade_pct_at(course: Course, pos: tuple[float, float]) -> float:
    """Elevation grade near the trail, from the slope between the points either side of the
    nearest one. 0.0 off-trail — there's no elevation data off the mapped course."""
    idx, dist_km = _nearest_point_idx(course, pos)
    if dist_km > TRAIL_PROXIMITY_KM:
        return 0.0
    points = course.points
    prev_p, next_p = points[max(0, idx - 1)], points[min(len(points) - 1, idx + 1)]
    run_km = next_p.cum_km - prev_p.cum_km
    if run_km <= 0:
        return 0.0
    rise_km = (next_p.elevation_m - prev_p.elevation_m) / 1000
    return (rise_km / run_km) * 100


def advance_position(
    pos: tuple[float, float], bearing_deg: float, distance_km: float
) -> tuple[float, float]:
    """Move `pos` by `distance_km` along compass bearing `bearing_deg`. haversine's Direction
    is radians clockwise from north (0=N, pi/2=E) — the same convention as bearing_deg, so no
    remapping is needed beyond degrees-to-radians."""
    if distance_km <= 0:
        return pos
    return inverse_haversine(
        pos, distance_km, math.radians(bearing_deg % 360), unit=Unit.KILOMETERS
    )


def books_found_this_tick(
    course: Course, pos: tuple[float, float], already_found: frozenset[int]
) -> tuple[frozenset[int], bool]:
    found = set(already_found)
    has_found_new = False
    for book in course.books:
        if (
            book.index not in found
            and haversine(pos, (book.lat, book.lon), unit=Unit.KILOMETERS) <= BOOK_PROXIMITY_KM
        ):
            found.add(book.index)
            has_found_new = True

    return frozenset(found), has_found_new


def detect_special_event(
    terrain: str, grade_pct: float, is_daylight: bool, rng: Random
) -> str | None:
    """Rare comedic events, rolled once per tick — only called when no book was found this
    tick (found_book takes priority, see sim/loop.py's advance_tick). Checked in a fixed
    priority order, each an early return, so at most one fires per tick — the string values
    match models.EventType (not imported here to avoid sim/ <-> models.py circularity).

    Terrain/grade-gated checks only roll on qualifying ground; dropped_water_bottle is
    ungated (any terrain, any time) and checked last, as the special event of last resort."""
    if (
        terrain in TRIP_TERRAIN or abs(grade_pct) >= TRIP_GRADE_PCT_THRESHOLD
    ) and rng.random() < TRIP_CHANCE_PER_TICK:
        return "tripped_and_fell"
    if terrain in PUDDLE_TERRAIN and rng.random() < PUDDLE_CHANCE_PER_TICK:
        return "stepped_in_puddle"
    if terrain in BRIAR_TERRAIN and rng.random() < BRIAR_CHANCE_PER_TICK:
        return "briar_scratch"
    if not is_daylight and rng.random() < WILDLIFE_CHANCE_PER_TICK:
        return "spooked_by_wildlife"
    if rng.random() < BOTTLE_DROP_CHANCE_PER_TICK:
        return "dropped_water_bottle"
    return None


def loop_completed(
    course: Course, pos: tuple[float, float], dist_since_loop_start_km: float
) -> bool:
    """A loop counts as done once you've covered a real fraction of it (not just standing
    near the start at minute 0) AND you're back within range of the start/finish point."""
    if dist_since_loop_start_km < course.total_km * LOOP_COMPLETE_MIN_FRACTION:
        return False
    return haversine(pos, start_coords(course), unit=Unit.KILOMETERS) <= LOOP_COMPLETE_RADIUS_KM


def believed_position(
    true_pos: tuple[float, float],
    fog_pct: float,
    is_daylight: bool,
    elapsed_min: float,
    rng: Random,
) -> tuple[float, float]:
    """Noisy believed position — magnitude grows with fog, night, and elapsed time (a fatigue
    proxy; no sleep_debt field yet, see ADR-0001). Two rng draws (direction, offset), like the
    weather draws in frozen_head_state_park.py."""
    fatigue_km = min(elapsed_min / 60 * NOISE_FATIGUE_PER_HOUR_KM, NOISE_FATIGUE_CAP_KM)
    magnitude_km = (
        NOISE_BASE_KM
        + NOISE_FOG_SCALE_KM * (fog_pct / 100)
        + (0.0 if is_daylight else NOISE_NIGHT_KM)
        + fatigue_km
    )
    direction_rad = rng.uniform(0, 2 * math.pi)
    offset_km = rng.uniform(0, magnitude_km)
    return inverse_haversine(true_pos, offset_km, direction_rad, unit=Unit.KILOMETERS)
