"""Participant wraps a Persona with the ability to turn an Observation into a Decision.

complete() is the one place that touches the Anthropic SDK directly (CLAUDE.md: "cheap
insurance against ever wanting to swap providers, without adding an actual gateway") — it's a
free function, not a method, since it isn't persona-specific and every Participant shares it.

Uses messages.create() with a raw output_config JSON schema rather than the messages.parse()
convenience wrapper. Confirmed empirically: opentelemetry-instrumentation-anthropic (the
Langfuse tracing integration) only instruments .create(), not .parse() — using .parse() traced
nothing to Langfuse despite auth/setup being correct. Same structured-output guarantee either
way, .create() is just the one that's actually observable.
"""

import json
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from anthropic.types import Message

from agents.memory import format_observation, turns_to_messages
from agents.personas import Persona
from models import Decision, Observation

MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class BrainOutcome:
    """What decide() actually produced. `failure_reason` is for OUR persistence/debugging
    (db.py's turns.failure_reason column) — never shown to the LLM, and never affects
    behavior: CLAUDE.md's contract (no retries, caller keeps the old decision) is unchanged
    whether decision is None because of an API error or a schema mismatch. This just means
    we can tell the two apart later instead of both looking like an identical print() line
    that's gone the moment the process exits."""

    decision: Decision | None
    failure_reason: str | None = None


_client = AsyncAnthropic()

_DECISION_SCHEMA = Decision.model_json_schema()
_DECISION_SCHEMA["additionalProperties"] = False


async def complete(system: str, messages: list[dict]) -> Message:
    """Structured-output call via output_config — see module docstring for why .create()
    over .parse()."""
    return await _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        messages=messages,
        output_config={"format": {"type": "json_schema", "schema": _DECISION_SCHEMA}},
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
        self,
        obs: Observation,
        history: list[tuple[Observation, Decision]],
        summary: str = "",
    ) -> list[dict]:
        """Renders the ADR-0008 running summary (if any), prior turns (oldest first), and the
        current Observation into the message list. The persona's system prompt is passed
        separately to complete() — the Anthropic API takes `system` as its own top-level
        param, not as a message."""
        messages = []
        if summary:
            messages.append({"role": "user", "content": f"Summary of the race so far:\n{summary}"})
        messages += turns_to_messages(history)
        messages.append({"role": "user", "content": format_observation(obs)})
        return messages

    async def decide(
        self,
        obs: Observation,
        history: list[tuple[Observation, Decision]] = (),
        summary: str = "",
    ) -> BrainOutcome:
        """Ask the LLM for a Decision, given the current Observation, prior turns, and the
        running compacted summary (ADR-0008). Returns a BrainOutcome with decision=None on any
        failure (API error, schema mismatch) — CLAUDE.md: no retries, caller keeps the old
        decision and logs a funny line instead. failure_reason is set alongside for db.py to
        persist (see BrainOutcome's docstring) — it never changes this method's behavior."""
        messages = self.build_prompt(obs, history, summary)
        try:
            response = await complete(system=self.persona.system_prompt_template, messages=messages)
            text = next(block.text for block in response.content if block.type == "text")
            return BrainOutcome(decision=Decision.model_validate(json.loads(text)))
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            print(f"[{self.persona.name}] brain call failed ({reason})")
            return BrainOutcome(decision=None, failure_reason=reason)
