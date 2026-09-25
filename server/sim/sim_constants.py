"Single source of truth for things we will be keeping constant so that its easy to change"

WEATHER_OFFSETS = {
    "clear": 0,
    "overcast": -2,
    "rain": -4,
    "storm": -6,
    "fog": -3,
}

WEATHER_CONDITIONS = tuple(WEATHER_OFFSETS)

# just random,  can tune as needed
TRANSITION_WEIGHTS = {
    "clear": {"clear": 90, "overcast": 8, "rain": 1, "storm": 0, "fog": 1},
    "overcast": {"clear": 20, "overcast": 60, "rain": 15, "storm": 2, "fog": 3},
    "rain": {"clear": 5, "overcast": 20, "rain": 60, "storm": 10, "fog": 5},
    "storm": {"clear": 1, "overcast": 5, "rain": 20, "storm": 70, "fog": 4},
    "fog": {"clear": 5, "overcast": 10, "rain": 5, "storm": 1, "fog": 79},
}

# sim/course.py (ADR-0010) — GPX resampling, book placement, terrain/loop detection, and
# believed-position noise. Raw track is ~16k points; resampling keeps per-tick nearest-point
# scans (terrain/grade) cheap instead of walking the whole thing every tick.
RESAMPLE_INTERVAL_KM = 0.05

N_BOOKS = 13  # matches the real Barkley's book count
BOOK_PROXIMITY_KM = 0.05  # how close you need to walk to a book to find it
TRAIL_PROXIMITY_KM = 0.1  # beyond this from the nearest trail point, you're "off trail"
LOOP_COMPLETE_RADIUS_KM = 0.1
# must have covered at least half the loop to "complete" it
LOOP_COMPLETE_MIN_FRACTION = 0.5

# Believed-position noise (comedy engine): base wobble + fog/night/fatigue add-ons, in km.
NOISE_BASE_KM = 0.02
NOISE_FOG_SCALE_KM = 0.15  # at fog_pct=100
NOISE_NIGHT_KM = 0.05
NOISE_FATIGUE_PER_HOUR_KM = 0.001
NOISE_FATIGUE_CAP_KM = 0.1

TERRAIN_LABELS = (
    "gravel road, gentle climb",
    "thick briars",
    "creek crossing",
    "steep scree",
    "overgrown singletrack",
    "pine thicket",
    "rocky ridge line",
    "muddy switchbacks",
)
OFF_TRAIL_TERRAIN = "thick brush, no trail in sight"

# Special events (comedic, non-book): rolled once per tick, after book-finding (which takes
# priority — see sim/course.py's detect_special_event and models.EventType). Terrain/grade-gated
# ones only get an rng roll on qualifying ground; kept deliberately rare at TICK_DT_MIN=0.25 so
# these read as occasional color, not a running commentary track.
TRIP_TERRAIN = frozenset(
    {"steep scree", "muddy switchbacks", "rocky ridge line", OFF_TRAIL_TERRAIN}
)
# abs(grade) beyond this also counts as trip-prone
TRIP_GRADE_PCT_THRESHOLD = 12.0
TRIP_CHANCE_PER_TICK = 0.02

PUDDLE_TERRAIN = frozenset({"creek crossing", "muddy switchbacks"})
PUDDLE_CHANCE_PER_TICK = 0.03

BRIAR_TERRAIN = frozenset({"thick briars"})
BRIAR_CHANCE_PER_TICK = 0.04

WILDLIFE_CHANCE_PER_TICK = 0.006  # night only, any terrain

BOTTLE_DROP_CHANCE_PER_TICK = 0.002  # ungated — any terrain, any time

# Sleep-debt hallucinations (ADR-0001/ADR-0008/ADR-0017): gated by elapsed_min alone (no
# separate sleep_debt field — same fatigue-proxy reasoning as NOISE_FATIGUE_PER_HOUR_KM above).
# Severity ramps 0.0 -> 1.0 between onset and cap, and drives both Observation.hallucination's
# per-tick chance and how badly a just-folded compaction segment gets jumbled.
#
# CLAUDE.md/ADR-0001's real target is "past ~40h" (2400 min) for a full 60h race; these are
# deliberately lower for dev-slice testing (a 75-min/300-tick run can actually trigger them) —
# flip to the commented-out "real" values once running full-length races.
HALLUCINATION_ONSET_MIN = 60.0  # real target: 40 * 60 = 2400.0
HALLUCINATION_RAMP_MIN = 240.0  # real target: 55 * 60 = 3300.0
HALLUCINATION_MAX_CHANCE_PER_TICK = 0.02
JUMBLE_MAX_SEVERITY = 0.6  # cap so a jumbled segment stays legible-if-unreliable, not pure noise
