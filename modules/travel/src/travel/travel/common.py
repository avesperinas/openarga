from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

Mode = Literal["plane", "train", "car", "bus", "boat"]
Category = Literal["transport", "lodging", "other"]
Source = Literal["app", "tool"]
Status = Literal["plan", "confirmed"]
Phase = Literal["plan", "upcoming", "ongoing", "done"]

MODES: tuple[Mode, ...] = ("plane", "train", "car", "bus", "boat")
CATEGORIES: dict[Category, tuple[str, ...]] = {
    "transport": ("Vuelos", "Coche", "Gasolina y parking", "Ferry", "Tren", "Bus"),
    "lodging": ("Hotel", "Apartamento"),
    "other": ("Efectivo", "Excursiones", "Seguro y vacunas", "Otros"),
}


MADRID = ZoneInfo("Europe/Madrid")


def today() -> date:
    return datetime.now(UTC).astimezone(MADRID).date()


def phase_of(status: str, starts_on: date, ends_on: date, on: date | None = None) -> Phase:
    if status == "plan":
        return "plan"
    day = on or today()
    if day < starts_on:
        return "upcoming"
    return "ongoing" if day <= ends_on else "done"


class NotFound(Exception):
    code = "NOT_FOUND"
    conflicts: list[dict] = []


class Conflict(Exception):
    def __init__(self, message: str, code: str = "INVALID", conflicts: list[dict] | None = None):
        super().__init__(message)
        self.code = code
        self.conflicts = conflicts or []


def _clean_list(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        one = " ".join(value.split())
        if one and one.lower() not in {s.lower() for s in seen}:
            seen.append(one)
    return seen
