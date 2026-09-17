"""Participant wraps a Persona with the ability to turn an Observation into a Decision.

complete() is the one place that touches the Anthropic SDK directly (CLAUDE.md: "cheap
insurance against ever wanting to swap providers, without adding an actual gateway") — it's a
free function, not a method, since it isn't persona-specific and every Participant shares it.
"""

from anthropic import AsyncAnthropic
from anthropic.types import ParsedMessage

from agents.personas import Persona
from models import Decision, Observation

MODEL = "claude-haiku-4-5-20251001"

_client = AsyncAnthropic()


async def complete(system: str, messages: list[dict]) -> ParsedMessage[Decision]:
    """Structured-output call: response.parsed_output is a validated Decision, no
    tool-call/JSON-parsing detour needed."""
    return await _client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
        output_format=Decision,
    )


def format_observation(obs: Observation) -> str:
    """Render an Observation as plain text for the user turn. Framed as the runner's own
    perception ("your body and surroundings"), not as someone speaking to them — the `user`
    role here just carries this turn's input, per the API's user/assistant/system roles; it
    doesn't mean a person is addressing the persona. Kept separate from build_prompt so it's
    easy to unit-test/tweak the wording independently."""
    lines = [
        "Your body and surroundings, right now:",
        f"Elapsed: {obs.elapsed_min} min, loop {obs.loop}, {obs.books_found} books found.",
        f"HR {obs.hr}, pace {obs.pace_min_per_km:.1f} min/km, cadence {obs.cadence}.",
        f"You feel: {obs.feel}. Last ate {obs.last_ate_min_ago} min ago.",
        f"Bearing {obs.bearing_deg:.0f} degrees. Believed position: {obs.gps_guess}.",
        f"Terrain: {obs.terrain}. Weather: {obs.weather}.",
    ]
    return "\n".join(lines)


class Participant:
    """A persona-driven decision-maker. One Participant per runner."""

    def __init__(self, persona: Persona):
        self.persona = persona

    def build_prompt(self, obs: Observation) -> list[dict]:
        """Renders the Observation into the message list. The persona's system prompt is
        passed separately to complete() — the Anthropic API takes `system` as its own
        top-level param, not as a message."""
        return [{"role": "user", "content": format_observation(obs)}]

    async def decide(self, obs: Observation) -> Decision | None:
        """Ask the LLM for a Decision. Returns None on any failure (API error, schema
        mismatch) — CLAUDE.md: no retries, caller keeps the old decision and logs a funny
        line instead."""
        messages = self.build_prompt(obs)
        try:
            response = await complete(system=self.persona.system_prompt_template, messages=messages)
            return response.parsed_output
        except Exception:
            return None
