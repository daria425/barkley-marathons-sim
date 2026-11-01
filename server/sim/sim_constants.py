"Single source of truth for things we will be keeping constant so that its easy to change"

WEATHER_OFFSETS = {
    "clear": 0,
    "overcast": -2,
    "rain": -4,
    "storm": -6,
    "fog": -3,
}

WEATHER_CONDITIONS = tuple(WEATHER_OFFSETS)

# sim/course.py (ADR-0010) — GPX resampling, book placement, terrain/loop detection, and
# believed-position noise. Raw track is ~16k points; resampling keeps per-tick nearest-point
# scans (terrain/grade) cheap instead of walking the whole thing every tick.
RESAMPLE_INTERVAL_KM = 0.05

N_BOOKS = 13  # matches the real Barkley's book count
# How close you need to walk to a book to find it. Only the end-of-tick position is checked, so
# this is sized against the max step per tick (0.1km at the 5 min/km pace floor with
# TICK_DT_MIN=0.5, ADR-0020): 0.075 keeps a straight pass from slipping through, while staying
# far below the ~2.3km book spacing (ADR-0015).
BOOK_PROXIMITY_KM = 0.075
TRAIL_PROXIMITY_KM = 0.1  # beyond this from the nearest trail point, you're "off trail"
LOOP_COMPLETE_RADIUS_KM = 0.1
# must have covered at least half the loop to "complete" it
LOOP_COMPLETE_MIN_FRACTION = 0.5

# ADR-0019: race rule, not a course-shape fact — sim/course.py stays ignorant of how many loops
# a race requires (it only detects when ONE loop completes); sim/loop.py's tick loop is what
# compares state.loop against this to decide "finished".
TOTAL_LOOPS = 5

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

# Sleep-debt memory jumbling (ADR-0017): gated by elapsed_min alone (no separate sleep_debt
# field — same fatigue-proxy reasoning as NOISE_FATIGUE_PER_HOUR_KM above). Severity ramps
# 0.0 -> 1.0 between onset and cap and drives how badly a just-folded compaction segment gets
# jumbled. Hallucination *lines* no longer use it: they fire from the race config's fixed
# schedule (ADR-0024), whose study-01 draft also starts at 40h.
HALLUCINATION_ONSET_MIN = 40 * 60.0
HALLUCINATION_RAMP_MIN = 55 * 60.0
JUMBLE_MAX_SEVERITY = 0.6  # cap so a jumbled segment stays legible-if-unreliable, not pure noise
