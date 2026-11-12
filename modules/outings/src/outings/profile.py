from __future__ import annotations

import os
import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from arga_module import preferences

DEFAULT = "pamplona"

Box = tuple[float, float, float, float]
Zone = Literal["near", "region"]


def folder() -> Path:
    given = os.environ.get("OUTINGS_AREAS")
    return Path(given) if given else Path(__file__).resolve().parents[2] / "areas"


def fold(value: str | None) -> str:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", plain.casefold()).split())


class Near(BaseModel):
    name: str
    contains: list[str] = []
    towns: list[str]
    box: Box


class Region(BaseModel):
    name: str
    towns: list[str]
    box: Box


class Piece(BaseModel):
    box: Box
    maxzoom: int


class Contours(BaseModel):
    coverage: str
    every: int


class Relief(BaseModel):
    wcs: str
    attribution: str
    near: Contours
    region: Contours


class Map(BaseModel):
    near: Piece
    region: Piece
    relief: Relief | None = None


class Agenda(BaseModel):
    name: str
    url: str


class Searches(BaseModel):
    always: list[str]
    monthly: list[str]
    yearly: list[str]
    season: str
    tradition: str


class Profile(BaseModel):
    id: str
    name: str
    country: str
    region_code: str | None = None
    language: str
    timezone: str
    geocoding: str
    near: Near
    region: Region
    map: Map
    focus: str
    include: str
    skip: str
    agendas: list[Agenda]
    months: list[str] = Field(min_length=12, max_length=12)
    searches: Searches
    season: dict[int, list[str]]
    traditions: dict[int, list[str]]

    def zone(self, town: str | None) -> Zone:
        folded = fold(town)
        if not folded:
            return "region"
        if folded in _near_towns(self.id) or any(one in folded for one in self.near.contains):
            return "near"
        return "region"


@cache
def _near_towns(area_id: str) -> frozenset[str]:
    return frozenset(fold(one) for one in load(area_id).near.towns)


def ids() -> list[str]:
    return sorted(path.stem for path in folder().glob("*.yaml"))


@cache
def load(area_id: str) -> Profile:
    path = folder() / f"{area_id}.yaml"
    return Profile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def resolve(asked: str | None) -> str:
    wanted = fold(asked).replace(" ", "-")
    return wanted if wanted in ids() else DEFAULT


def current() -> Profile:
    return load(resolve(preferences.current().area))
