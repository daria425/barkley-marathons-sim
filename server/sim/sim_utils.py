"Shared utils so that we dont duplicate"


def calculate_hour(start_hour: float, elapsed_min: float) -> float:
    hour = (start_hour + elapsed_min / 60) % 24
    return hour
