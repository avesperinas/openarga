from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

from shopping.catalog import t

ENOUGH = 3


@dataclass(frozen=True)
class Habit:
    times: int
    last: date | None
    every_days: float | None

    def since(self, today: date) -> int | None:
        return None if self.last is None else (today - self.last).days

    def due(self, today: date) -> bool:
        since = self.since(today)
        return self.every_days is not None and since is not None and since >= self.every_days

    def overdue(self, today: date) -> float:
        since = self.since(today)
        if self.every_days is None or since is None:
            return 0.0
        return since / self.every_days


def habit(bought: list[date]) -> Habit:
    days = sorted(set(bought))
    if not days:
        return Habit(times=0, last=None, every_days=None)
    gaps = [(later - earlier).days for earlier, later in zip(days, days[1:], strict=False)]
    every = float(median(gaps)) if len(days) >= ENOUGH else None
    return Habit(times=len(days), last=days[-1], every_days=every)


def every_label(every_days: float | None) -> str | None:
    if every_days is None:
        return None
    days = round(every_days)
    if days <= 1:
        return t("every.day")
    if days % 7 == 0 and days >= 14:
        return t("every.weeks", weeks=days // 7)
    if days == 7:
        return t("every.week")
    return t("every.days", days=days)


def since_label(since: int | None) -> str | None:
    if since is None:
        return None
    if since <= 0:
        return t("since.today")
    if since == 1:
        return t("since.yesterday")
    return t("since.days", days=since)
