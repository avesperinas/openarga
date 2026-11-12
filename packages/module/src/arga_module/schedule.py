from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

FIELDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


class InvalidSchedule(ValueError):
    pass


@dataclass(frozen=True)
class Schedule:
    expression: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    days_restricted: bool
    weekdays_restricted: bool

    @classmethod
    def parse(cls, expression: str) -> Schedule:
        parts = expression.split()
        if len(parts) != 5:
            raise InvalidSchedule(f"'{expression}': un cron lleva cinco campos")
        sets = [
            _field(part, low, high, expression)
            for part, (low, high) in zip(parts, FIELDS, strict=True)
        ]
        weekdays = frozenset(7 if day == 0 else day for day in sets[4])
        return cls(
            expression,
            *sets[:4],
            weekdays,
            days_restricted=parts[2] != "*",
            weekdays_restricted=parts[4] != "*",
        )

    def matches(self, moment: datetime) -> bool:
        weekday = moment.isoweekday()
        if self.days_restricted and self.weekdays_restricted:
            day_ok = moment.day in self.days or weekday in self.weekdays
        else:
            day_ok = moment.day in self.days and weekday in self.weekdays
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.month in self.months
            and day_ok
        )


def _field(part: str, low: int, high: int, expression: str) -> frozenset[int]:
    values: set[int] = set()
    for chunk in part.split(","):
        body, _, step_text = chunk.partition("/")
        try:
            step = int(step_text) if step_text else 1
            if body == "*":
                start, end = low, high
            elif "-" in body:
                start, end = (int(value) for value in body.split("-", 1))
            else:
                start = end = int(body)
        except ValueError as error:
            raise InvalidSchedule(f"'{expression}': no entiendo '{chunk}'") from error
        if step < 1 or start < low or end > high or start > end:
            raise InvalidSchedule(f"'{expression}': '{chunk}' se sale de {low}-{high}")
        values.update(range(start, end + 1, step))
    return frozenset(values)
