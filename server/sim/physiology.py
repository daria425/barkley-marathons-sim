"""Pure physiology functions. No knowledge of effort's source."""

from dataclasses import dataclass

BONK_GLYCOGEN_PCT = 20.0
BONK_PUSH_EFFORT_THRESHOLD = 7  # RPE at/above this while bonking counts as "pushing through it"
BONK_PUSH_LIMIT_MIN = 30.0  # sim-minutes of pushing through a bonk before the body overrides you

# Drain rates, rough real ultrarunning numbers. Glycogen: ~2,000 kcal of stored carbohydrate
# lasts ~1.5h flat out and ~2.5-3h at a steady effort, so a runner who never eats bonks around
# then. Hydration: sweat loss of ~0.3 L/h in the cold up to ~1.5 L/h in heat, against a ~3 L
# deficit treated as 100%.
GLYCOGEN_DRAIN_PCT_PER_HR_PER_EFFORT = 6.0  # effort 5 -> 30%/h, bonks after ~2h40 unfed
HYDRATION_DRAIN_BASE_PCT_PER_HR = 10.0  # cold weather (heat 0)
HYDRATION_DRAIN_PCT_PER_HR_PER_HEAT = 4.0  # heat 3 -> 22%/h, heat 7 -> 38%/h

# Dehydration (ADR-0025): thirst shows from THIRSTY_PCT; pace suffers below DEHYDRATED_PCT and
# more below SEVERELY_DEHYDRATED_PCT, stacking with a bonk.
THIRSTY_PCT = 60.0
DEHYDRATED_PCT = 40.0
SEVERELY_DEHYDRATED_PCT = 20.0
DEHYDRATED_PACE_FACTOR = 1.3
SEVERELY_DEHYDRATED_PACE_FACTOR = 1.6


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
    depletion = effort_rpe * GLYCOGEN_DRAIN_PCT_PER_HR_PER_EFFORT * (dt_min / 60)
    refill = 15.0 if ate else 0.0
    return min(100.0, max(0.0, glycogen_pct - depletion + refill))


def step_hydration(hydration_pct: float, heat: int, dt_min: float, drank: bool) -> float:
    """Drains faster with heat; drinking refills it. Never below 0."""
    depletion = (HYDRATION_DRAIN_BASE_PCT_PER_HR + heat * HYDRATION_DRAIN_PCT_PER_HR_PER_HEAT) * (
        dt_min / 60
    )
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


def describe_feel(glycogen_pct: float, collapsed: bool) -> str:
    """Text label for Observation.feel — kept next to is_bonking/has_collapsed since it
    directly depends on their thresholds, rather than duplicated at the call site."""
    if collapsed:
        return "collapsed, body won't listen anymore"
    if is_bonking(glycogen_pct):
        return "bonking"
    if glycogen_pct < 50.0:
        return "legs heavy"
    return "feeling good"


def describe_thirst(hydration_pct: float) -> str:
    """Text label for Observation.thirst, the model's only view of hydration."""
    if hydration_pct < SEVERELY_DEHYDRATED_PCT:
        return "dizzy, badly dehydrated"
    if hydration_pct < DEHYDRATED_PCT:
        return "dry mouth, head pounding"
    if hydration_pct < THIRSTY_PCT:
        return "thirsty"
    return "not thirsty"


def dehydration_pace_factor(hydration_pct: float) -> float:
    if hydration_pct < SEVERELY_DEHYDRATED_PCT:
        return SEVERELY_DEHYDRATED_PACE_FACTOR
    if hydration_pct < DEHYDRATED_PCT:
        return DEHYDRATED_PACE_FACTOR
    return 1.0


def compute_pace(
    start_pace_min_per_km: float,
    effort_rpe: int,
    glycogen_pct: float,
    collapsed: bool = False,
    grade_pct: float = 0.0,
    hydration_pct: float = 100.0,
) -> float:
    """Pace (min/km) from effort, adjusted for bonking, dehydration, collapse, grade. Higher
    number = slower. The fastest-pace floor applies to the effort pace before the bonk and
    dehydration penalties; applied after, it swallowed them at effort 10 (ADR-0025)."""
    if collapsed:
        return start_pace_min_per_km * 4  # body overrides effort entirely
    fastest = start_pace_min_per_km * 0.5
    effort_factor = 11 - effort_rpe  # RPE 10 -> fast, RPE 1 -> slow
    pace = max(start_pace_min_per_km * (effort_factor / 5), fastest)
    if is_bonking(glycogen_pct):
        pace *= 1.8
    pace *= dehydration_pace_factor(hydration_pct)
    pace += grade_pct * 0.05
    return max(pace, fastest)


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
