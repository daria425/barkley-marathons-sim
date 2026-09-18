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
LOOP_COMPLETE_MIN_FRACTION = 0.5  # must have covered at least half the loop to "complete" it

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
