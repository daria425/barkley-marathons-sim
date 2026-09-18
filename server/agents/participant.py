"""Participant wraps a Persona with the ability to turn an Observation into a Decision.

complete() is the one place that touches the Anthropic SDK directly (CLAUDE.md: "cheap
insurance against ever wanting to swap providers, without adding an actual gateway") — it's a
free function, not a method, since it isn't persona-specific and every Participant shares it.
"""

from anthropic import AsyncAnthropic
from anthropic.types import ParsedMessage

from agents.memory import format_observation, turns_to_messages
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


class Participant:
    """A persona-driven decision-maker. One Participant per runner.

    Stays DB-agnostic on purpose (matches CLAUDE.md's module split: db.py owns storage,
    agents/memory.py owns prompt-shaping, this file just calls the LLM) — the caller (loop.py)
    is responsible for pulling history from db.get_recent_turns and passing it in.
    """

    def __init__(self, persona: Persona):
        self.persona = persona

    def build_prompt(
        self, obs: Observation, history: list[tuple[Observation, Decision]]
    ) -> list[dict]:
        """Renders prior turns (oldest first) plus the current Observation into the message
        list. The persona's system prompt is passed separately to complete() — the Anthropic
        API takes `system` as its own top-level param, not as a message."""
        return turns_to_messages(history) + [{"role": "user", "content": format_observation(obs)}]

    async def decide(
        self, obs: Observation, history: list[tuple[Observation, Decision]] = ()
    ) -> Decision | None:
        """Ask the LLM for a Decision, given the current Observation and prior turns. Returns
        None on any failure (API error, schema mismatch) — CLAUDE.md: no retries, caller keeps
        the old decision and logs a funny line instead."""
        messages = self.build_prompt(obs, history)
        try:
            response = await complete(system=self.persona.system_prompt_template, messages=messages)
            return response.parsed_output
        except Exception:
            return None
