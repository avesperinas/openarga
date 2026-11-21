from __future__ import annotations

import dataclasses
import importlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

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
    copy: str | None = None
    roster: tuple[tuple[str, UUID], ...] = ()

    @property
    def seed_key(self) -> str:
        # Seeds derive their row ids from this, so two copies of the cast never share an id.
        return self.key if self.copy is None else f"{self.copy}:{self.key}"

    def id_of(self, key: str) -> UUID:
        return dict(self.roster)[key]


@dataclass(frozen=True)
class Cast:
    space_id: UUID
    space_name: str
    people: tuple[Persona, ...]
    copy: str | None = None


Seed = Callable[[Any, Persona, date], Awaitable[None]]

COPIES = UUID("0b7c0de5-0000-4000-8000-00000000c0b1")
COPY_TAG = re.compile(r"^[a-z0-9]{6,16}$")


def load(path: Path) -> Cast:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    people = tuple(
        Persona(**{**person, "id": UUID(str(person["id"]))}) for person in data["people"]
    )
    roster = tuple((person.key, person.id) for person in people)
    people = tuple(dataclasses.replace(person, roster=roster) for person in people)
    return Cast(UUID(str(data["space"]["id"])), data["space"]["name"], people)


def copy_of(cast: Cast, tag: str, locale: str | None = None) -> Cast:
    if not COPY_TAG.match(tag):
        raise ValueError(f"not a copy tag: {tag!r}")
    ids = {person.key: uuid5(COPIES, f"{tag}:{person.key}") for person in cast.people}
    roster = tuple(ids.items())
    people = tuple(
        dataclasses.replace(
            person,
            id=ids[person.key],
            username=f"{tag}-{person.username}",
            locale=locale or person.locale,
            copy=tag,
            roster=roster,
        )
        for person in cast.people
    )
    return Cast(uuid5(COPIES, f"{tag}:space"), cast.space_name, people, tag)


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
