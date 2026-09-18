"""Personas are data (YAML), not Python constants — see CLAUDE.md's Personas section.
This module only loads and validates them.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


class Persona(BaseModel):
    name: str
    bib_number: int  # real Barkley bibs are odd numbers — see ADR-0010
    traits: list[str]
    system_prompt_template: str


def load_persona(path: Path) -> Persona:
    with path.open() as f:
        data = yaml.safe_load(f)
    return Persona.model_validate(data)
