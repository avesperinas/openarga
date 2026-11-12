from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml


@dataclass(frozen=True)
class Persona:
    key: str
    id: UUID
    name: str
    username: str
    locale: str
    timezone: str
    currency: str
    country: str | None
    region: str | None
    area: str | None


@dataclass(frozen=True)
class Cast:
    space_id: UUID
    space_name: str
    people: tuple[Persona, ...]


Seed = Callable[[Any, Persona, date], Awaitable[None]]


def load(path: Path) -> Cast:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    people = tuple(
        Persona(**{**person, "id": UUID(str(person["id"]))}) for person in data["people"]
    )
    return Cast(UUID(str(data["space"]["id"])), data["space"]["name"], people)


def seeds(modules: Path) -> dict[str, Seed]:
    found: dict[str, Seed] = {}
    for manifest in sorted(modules.glob("[a-z]*/manifest.yaml")):
        module_id = manifest.parent.name
        if not (manifest.parent / "src" / module_id / "demo.py").exists():
            continue
        found[module_id] = importlib.import_module(f"{module_id}.demo").seed
    return found
