"""Tests for Participant.decide()'s failure contract (CLAUDE.md: no retries, return a
BrainOutcome with decision=None, caller keeps the old decision) across the different ways a
brain call can actually fail — an API-level error, a response that isn't valid JSON, and JSON
that doesn't match the Decision schema. All three must produce decision=None from the caller's
point of view, but each carries its own distinguishable failure_reason (db.py persists this —
see db.log_turn's docstring), rather than looking identical the way a bare print() line used
to. These tests exercise the failure paths, not just the happy path, without ever hitting the
real API (agents.participant.complete is monkeypatched).
"""

import asyncio
import json

import agents.participant as participant_module
from agents.participant import Participant
from agents.personas import Persona
from models import Decision, Observation


def _persona() -> Persona:
    return Persona(
        name="Test", bib_number=1, traits=[], system_prompt_template="You are a test runner."
    )


def _obs() -> Observation:
    return Observation(
        elapsed_min=0,
        clock_time="Day 1, 12:00 AM",
        hr=100,
        pace_min_per_km=10.0,
        cadence=170,
        feel="feeling good",
        last_ate_min_ago=0,
        bearing_deg=0.0,
        gps_guess=(0.0, 0.0),
        terrain="gravel road",
        weather="clear",
        books_found=0,
        loop=1,
        hallucination=None,
    )


class _FakeBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


def test_decide_returns_none_with_reason_on_api_error(monkeypatch, capsys):
    async def fake_complete(system, messages):
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(participant_module, "complete", fake_complete)

    outcome = asyncio.run(Participant(_persona()).decide(_obs()))

    assert outcome.decision is None
    assert "RuntimeError" in outcome.failure_reason
    assert "RuntimeError" in capsys.readouterr().out


def test_decide_returns_none_with_reason_on_invalid_json(monkeypatch):
    async def fake_complete(system, messages):
        return _FakeMessage("not json at all")

    monkeypatch.setattr(participant_module, "complete", fake_complete)

    outcome = asyncio.run(Participant(_persona()).decide(_obs()))

    assert outcome.decision is None
    assert outcome.failure_reason  # some reason is recorded, exact text isn't the contract


def test_decide_returns_none_with_reason_on_schema_mismatch(monkeypatch):
    async def fake_complete(system, messages):
        return _FakeMessage(json.dumps({"effort": 5}))  # missing required Decision fields

    monkeypatch.setattr(participant_module, "complete", fake_complete)

    outcome = asyncio.run(Participant(_persona()).decide(_obs()))

    assert outcome.decision is None
    assert outcome.failure_reason


def test_decide_returns_decision_and_no_failure_reason_on_success(monkeypatch):
    """Confirms the monkeypatch harness itself is wired correctly, not just that failures
    return decision=None."""
    valid = Decision(
        effort=5, eat=False, drink=True, bearing_deg=0.0, rest_min=0, quit=False, monologue="ok"
    )

    async def fake_complete(system, messages):
        return _FakeMessage(valid.model_dump_json())

    monkeypatch.setattr(participant_module, "complete", fake_complete)

    outcome = asyncio.run(Participant(_persona()).decide(_obs()))

    assert outcome.decision == valid
    assert outcome.failure_reason is None
