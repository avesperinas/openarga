from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from arga_contracts import notify
from arga_module import preferences


def zone() -> ZoneInfo:
    person = preferences.current()
    return person.zone if person != preferences.defaults() else notify.zone()


def now() -> datetime:
    return datetime.now(zone())


def today() -> date:
    return now().date()
