"""Pure physiology functions. No knowledge of effort's source."""

from dataclasses import dataclass

BONK_GLYCOGEN_PCT = 20.0
BONK_PUSH_EFFORT_THRESHOLD = 7  # RPE at/above this while bonking counts as "pushing through it"
BONK_PUSH_LIMIT_MIN = 30.0  # sim-minutes of pushing through a bonk before the body overrides you


@dataclass(frozen=True)
class PhysiologyState:
    elapsed_min: float
    hr: int
    glycogen_pct: float
    hydration_pct: float
    core_temp_c: float
    start_core_temp_c: float
    bonk_push_min: float


def initial_state() -> PhysiologyState:
    # same value for both so the first tick doesn't start with a temp jump
    start_core_temp_c = 37.0
    return PhysiologyState(
        elapsed_min=0.0,
        hr=0,
        glycogen_pct=100.0,
        hydration_pct=100.0,
        start_core_temp_c=start_core_temp_c,
        core_temp_c=start_core_temp_c,
        bonk_push_min=0.0,
    )


def step_heart_rate(base_hr: int, effort_rpe: int, heat: int, elapsed_min: float) -> int:
    """HR rises with effort, heat, and cardiac drift over elapsed time."""
    hr_increase = effort_rpe * 5
    heat_adjustment = heat * 2
    drift = elapsed_min / 60  # +1 bpm per hour of cardiac drift
    return round(base_hr + hr_increase + heat_adjustment + drift)


def step_glycogen(glycogen_pct: float, effort_rpe: int, dt_min: float, ate: bool) -> float:
    """Drains with effort over dt_min; eating refills it. Never below 0."""
    depletion = effort_rpe * 0.5 * (dt_min / 60)
    refill = 15.0 if ate else 0.0
    return min(100.0, max(0.0, glycogen_pct - depletion + refill))


def step_hydration(hydration_pct: float, heat: int, dt_min: float, drank: bool) -> float:
    """Drains faster with heat; drinking refills it. Never below 0."""
    depletion = (1.0 + heat * 0.3) * (dt_min / 60)
    refill = 20.0 if drank else 0.0
    return min(100.0, max(0.0, hydration_pct - depletion + refill))


def step_core_temp(
    start_core_temp_c: float, core_temp_c: float, effort_rpe: int, heat: int, dt_min: float
) -> float:
    """Rises with effort + heat, relaxes toward that target each tick."""
    target = start_core_temp_c + effort_rpe * 0.05 + heat * 0.1
    relax_rate = 0.1
    return core_temp_c + (target - core_temp_c) * relax_rate * (dt_min / 5)


def is_bonking(glycogen_pct: float) -> bool:
    return glycogen_pct < BONK_GLYCOGEN_PCT


def step_bonk_push(
    bonk_push_min: float, glycogen_pct: float, effort_rpe: int, dt_min: float
) -> float:
    """Accumulates while pushing hard through a bonk; resets the moment you back off or refuel."""
    pushing_through_bonk = is_bonking(glycogen_pct) and effort_rpe >= BONK_PUSH_EFFORT_THRESHOLD
    return bonk_push_min + dt_min if pushing_through_bonk else 0.0


def has_collapsed(bonk_push_min: float) -> bool:
    return bonk_push_min >= BONK_PUSH_LIMIT_MIN


def compute_pace(
    start_pace_min_per_km: float,
    effort_rpe: int,
    glycogen_pct: float,
    collapsed: bool = False,
    grade_pct: float = 0.0,
) -> float:
    """Pace (min/km) from effort, adjusted for bonking, collapse, grade. Higher number = slower."""
    if collapsed:
        return start_pace_min_per_km * 4  # body overrides effort entirely
    effort_factor = 11 - effort_rpe  # RPE 10 -> fast, RPE 1 -> slow
    pace = start_pace_min_per_km * (effort_factor / 5)
    if is_bonking(glycogen_pct):
        pace *= 1.8
    pace += grade_pct * 0.05
    return max(pace, start_pace_min_per_km * 0.5)


def tick(
    state: PhysiologyState,
    base_hr: int,
    effort_rpe: int,
    heat: int,
    dt_min: float,
    ate: bool = False,
    drank: bool = False,
) -> PhysiologyState:
    """Advance physiology by one tick. effort/eat/drink come from the Decision, not physiology."""
    elapsed_min = state.elapsed_min + dt_min
    glycogen_pct = step_glycogen(state.glycogen_pct, effort_rpe, dt_min, ate)
    return PhysiologyState(
        elapsed_min=elapsed_min,
        hr=step_heart_rate(base_hr, effort_rpe, heat, elapsed_min),
        glycogen_pct=glycogen_pct,
        hydration_pct=step_hydration(state.hydration_pct, heat, dt_min, drank),
        start_core_temp_c=state.start_core_temp_c,
        core_temp_c=step_core_temp(
            state.start_core_temp_c, state.core_temp_c, effort_rpe, heat, dt_min
        ),
        bonk_push_min=step_bonk_push(state.bonk_push_min, glycogen_pct, effort_rpe, dt_min),
    )
