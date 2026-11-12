from __future__ import annotations

import os
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from zoneinfo import ZoneInfo

from arga_module.i18n import LOCALES, SOURCE

HEADERS = {
    "locale": "x-arga-locale",
    "timezone": "x-arga-timezone",
    "currency": "x-arga-currency",
    "country": "x-arga-country",
    "region": "x-arga-region",
    "area": "x-arga-area",
}


@dataclass(frozen=True)
class Preferences:
    locale: str
    timezone: str
    currency: str
    country: str | None
    region: str | None
    area: str | None

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def defaults() -> Preferences:
    locale = os.environ.get("OPENARGA_LOCALE", SOURCE)
    return Preferences(
        locale=locale if locale in LOCALES else SOURCE,
        timezone=os.environ.get("OPENARGA_TIMEZONE", "UTC"),
        currency=os.environ.get("OPENARGA_CURRENCY", "EUR"),
        country=os.environ.get("OPENARGA_COUNTRY") or None,
        region=os.environ.get("OPENARGA_REGION") or None,
        area=os.environ.get("OPENARGA_AREA") or None,
    )


def from_headers(headers: Mapping[str, str]) -> Preferences:
    base = defaults()
    given = {field: headers.get(header) for field, header in HEADERS.items()}
    chosen = {field: value for field, value in given.items() if value}
    if chosen.get("locale") not in (None, *LOCALES):
        chosen.pop("locale")
    if "timezone" in chosen:
        try:
            ZoneInfo(chosen["timezone"])
        except (KeyError, ValueError):
            chosen.pop("timezone")
    return replace(base, **chosen)


_current: ContextVar[Preferences | None] = ContextVar("arga_preferences", default=None)


def current() -> Preferences:
    return _current.get() or defaults()


def use(preferences: Preferences) -> Token[Preferences | None]:
    return _current.set(preferences)


def reset(token: Token[Preferences | None]) -> None:
    _current.reset(token)
