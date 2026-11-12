from __future__ import annotations

from dataclasses import dataclass, field

LANES = ("hob", "oven", "air_fryer", "board", "bowl", "fridge", "none")


@dataclass(frozen=True)
class Step:
    position: int
    action: str
    text: str
    minutes: int
    attended: bool = True
    equipment: str = "none"
    after: tuple[int, ...] = ()
    ingredients: tuple[str, ...] = ()
    uses: tuple[int, ...] = ()


@dataclass(frozen=True)
class Scheduled:
    position: int
    action: str
    text: str
    minutes: int
    attended: bool
    equipment: str
    ingredients: tuple[str, ...]
    start: int
    end: int


@dataclass(frozen=True)
class Plan:
    steps: tuple[Scheduled, ...] = ()
    total_minutes: int = 0
    active_minutes: int = 0
    lanes: tuple[str, ...] = ()


def _in_order(steps: list[Step]) -> list[Step]:
    return sorted(steps, key=lambda step: step.position)


def schedule(steps: list[Step]) -> Plan:
    if not steps:
        return Plan()

    ends: dict[int, int] = {}
    cook_free = 0
    scheduled: list[Scheduled] = []

    for step in _in_order(steps):
        ready = max((ends[position] for position in step.after if position in ends), default=0)
        start = max(ready, cook_free) if step.attended else ready
        end = start + step.minutes
        ends[step.position] = end
        if step.attended:
            cook_free = end
        scheduled.append(
            Scheduled(
                position=step.position,
                action=step.action,
                text=step.text,
                minutes=step.minutes,
                attended=step.attended,
                equipment=step.equipment,
                ingredients=step.ingredients,
                start=start,
                end=end,
            )
        )

    used = [lane for lane in LANES if any(one.equipment == lane for one in scheduled)]
    return Plan(
        steps=tuple(scheduled),
        total_minutes=max(one.end for one in scheduled),
        active_minutes=sum(one.minutes for one in scheduled if one.attended),
        lanes=tuple(used),
    )


@dataclass
class Overlap:
    equipment: str
    positions: list[int] = field(default_factory=list)


def overlaps(plan: Plan) -> list[Overlap]:
    found: list[Overlap] = []
    for lane in plan.lanes:
        if lane == "none":
            continue
        inside = sorted(
            (one for one in plan.steps if one.equipment == lane), key=lambda one: one.start
        )
        clashing: set[int] = set()
        for index, one in enumerate(inside):
            for other in inside[index + 1 :]:
                if other.start < one.end:
                    clashing.update({one.position, other.position})
        if clashing:
            found.append(Overlap(equipment=lane, positions=sorted(clashing)))
    return found
