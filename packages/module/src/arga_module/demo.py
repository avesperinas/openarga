from __future__ import annotations

import dataclasses
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


def localizer(directory: Path) -> Callable[[Persona, str], str]:
    # Seeds are written in English; directory/es.json maps each line to Spanish for Sam.
    from arga_module.i18n import catalogs

    def say(persona: Persona, english: str) -> str:
        if persona.locale == "en":
            return english
        return catalogs(directory).get(persona.locale, {}).get(english) or english

    return say


def localized(say: Callable[[Persona, str], str], persona: Persona, value: Any) -> Any:
    if isinstance(value, str):
        return say(persona, value)
    if isinstance(value, list | tuple):
        return type(value)(localized(say, persona, item) for item in value)
    if isinstance(value, dict):
        return {key: localized(say, persona, item) for key, item in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
        return dataclasses.replace(value, **localized(say, persona, fields))
    if hasattr(value, "model_copy"):
        fields = {name: getattr(value, name) for name in type(value).model_fields}
        return value.model_copy(update=localized(say, persona, fields))
    return value
