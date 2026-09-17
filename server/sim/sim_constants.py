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
