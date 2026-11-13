from __future__ import annotations

from zoneinfo import ZoneInfo

from arga_contracts import notify
from arga_module import preferences


def home() -> ZoneInfo:
    person = preferences.current()
    return person.zone if person != preferences.defaults() else notify.zone()


def home_name() -> str:
    return home().key
