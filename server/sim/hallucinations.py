"""Sleep-debt hallucinations (ADR-0001, ADR-0008, ADR-0017).

Two independent mechanics, both gated by the same elapsed_min-driven severity curve (no
separate sleep_debt field — see believed_position's fatigue_km in sim/course.py for the same
"elapsed_min as fatigue proxy" reasoning):

1. `roll()` — a free-text Observation.hallucination string, injected straight into the prompt
   verbatim (see agents/memory.py's format_observation). Independent of Observation.event.
2. `jumble_text()` — degrades a compacted memory segment's rendered prose at the moment it's
   folded (agents/memory.py's compact_segment), so recent sliding-window turns stay accurate
   while older, already-folded memory reads increasingly unreliable. Seeded from a stable hash
   of the segment's own text, not Python's randomized `hash()`, so compaction stays a pure
   function of its inputs (ADR-0008) and resume (ADR-0009) stays bit-exact.
"""

import hashlib
import re
from random import Random

from sim.sim_constants import (
    HALLUCINATION_MAX_CHANCE_PER_TICK,
    HALLUCINATION_ONSET_MIN,
    HALLUCINATION_RAMP_MIN,
    JUMBLE_MAX_SEVERITY,
)

_HALLUCINATIONS = (
    "You see a bear watching you from the ridge. It waves back when you wave.",
    "You're certain you just passed your own house, though you've never been to Tennessee.",
    "A stranger in a yellow raincoat says you're almost done. There is no stranger.",
    "You hear someone laughing from somewhere in the trees. It sounds like Lazarus Lake.",
    "The trail markers spell out your bib number in a language you don't speak.",
    "You feel someone running just behind your left shoulder, matching your pace exactly.",
    "The moon looks like a slice of pizza. You are extremely hungry.",
    "You're briefly convinced this is a dream, and you're still asleep at the start line.",
    "A conversation with your mother from third grade replays in your head, word for word.",
    "You see the finish line. It's a mirage — you're only on loop 2.",
    "The trees are whispering your name.",
    "You feel very anxious for no describable reason.",
    "You could swear you just saw a vending machine in the middle of the woods.",
    "Your feet feel like they belong to someone else.",
    "You hear a phone ringing somewhere in the wilderness. There is no phone.",
)


def severity(elapsed_min: float) -> float:
    """0.0 at/before HALLUCINATION_ONSET_MIN, ramping linearly to 1.0 by HALLUCINATION_RAMP_MIN."""
    if elapsed_min <= HALLUCINATION_ONSET_MIN:
        return 0.0
    span = HALLUCINATION_RAMP_MIN - HALLUCINATION_ONSET_MIN
    return min(1.0, (elapsed_min - HALLUCINATION_ONSET_MIN) / span)


def roll(elapsed_min: float, rng: Random) -> str | None:
    """Per-tick hallucination chance, scaled by severity — call with the live sim rng, same
    convention as sim/course.py's detect_special_event."""
    chance = severity(elapsed_min) * HALLUCINATION_MAX_CHANCE_PER_TICK
    if rng.random() < chance:
        return rng.choice(_HALLUCINATIONS)
    return None


def jumble_severity_for(elapsed_min: float) -> float:
    """How badly a segment ending at `elapsed_min` should be jumbled — severity capped at
    JUMBLE_MAX_SEVERITY so a folded segment stays legible-if-unreliable, never pure noise."""
    return severity(elapsed_min) * JUMBLE_MAX_SEVERITY


_WORD_RE = re.compile(r"\w+|\W+")


def jumble_text(text: str, jumble_severity: float) -> str:
    """Deterministically garble `text` — localized word-swaps, digit misattribution, and
    occasional dropped words — standing in for unreliable, sleep-deprived memory rather than
    literal noise. `jumble_severity` in [0, 1]; 0 returns `text` unchanged.

    Seeded from a stable hash of `text` itself (not Python's per-process-randomized `hash()`),
    so this is a pure function of its inputs: same segment text + same severity always jumbles
    identically, which is what keeps ADR-0008's compaction deterministic and ADR-0009's resume
    bit-exact."""
    if jumble_severity <= 0:
        return text
    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    rng = Random(seed)

    tokens = _WORD_RE.findall(text)
    word_idxs = [i for i, t in enumerate(tokens) if t.strip() and t[0].isalnum()]

    # Localized adjacent word-swaps — reads as scrambled recall, not full shuffle.
    for a, b in zip(word_idxs, word_idxs[1:], strict=False):
        if rng.random() < jumble_severity * 0.3:
            tokens[a], tokens[b] = tokens[b], tokens[a]

    # Digit misattribution — "3 books" becomes "8 books" (ADR-0008's "misattributed entries").
    for i in word_idxs:
        if any(c.isdigit() for c in tokens[i]) and rng.random() < jumble_severity * 0.5:
            tokens[i] = "".join(str(rng.randint(0, 9)) if c.isdigit() else c for c in tokens[i])

    # Dropped words — a faded gap in the memory (ADR-0008's "faded monologue lines").
    for i in word_idxs:
        if rng.random() < jumble_severity * 0.15:
            tokens[i] = "..."

    return "".join(tokens)
