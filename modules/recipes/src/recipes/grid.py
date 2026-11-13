from __future__ import annotations

from dataclasses import dataclass

from recipes.catalog import t
from recipes.gantt import Step


@dataclass(frozen=True)
class Ingredient:
    position: int
    name: str


@dataclass(frozen=True)
class Row:
    position: int
    name: str
    orphan: bool = False


@dataclass(frozen=True)
class Cell:
    position: int
    action: str
    text: str
    minutes: int
    attended: bool
    equipment: str
    column: int
    row: int
    span: int


@dataclass(frozen=True)
class Band:
    position: int
    action: str
    text: str
    minutes: int
    attended: bool
    equipment: str


@dataclass(frozen=True)
class Grid:
    rows: tuple[Row, ...] = ()
    cells: tuple[Cell, ...] = ()
    bands: tuple[Band, ...] = ()
    columns: int = 0
    notes: tuple[str, ...] = ()


def _first_use(steps: list[Step]) -> tuple[dict[int, int], list[str]]:
    owner: dict[int, int] = {}
    repeated: dict[int, list[int]] = {}
    for step in sorted(steps, key=lambda one: one.position):
        for ingredient in step.uses:
            if ingredient in owner:
                repeated.setdefault(ingredient, []).append(step.position)
            else:
                owner[ingredient] = step.position
    return owner, [
        t("grid.ingredient_again", ingredient=ingredient, steps=_steps(positions))
        for ingredient, positions in sorted(repeated.items())
    ]


def _steps(positions: list[int]) -> str:
    return t("grid.and").join(str(position) for position in positions)


def _first_consumer(steps: list[Step]) -> tuple[dict[int, int], list[str]]:
    consumer: dict[int, int] = {}
    shared: dict[int, list[int]] = {}
    for step in sorted(steps, key=lambda one: one.position):
        for earlier in sorted(step.after):
            if earlier in consumer:
                shared.setdefault(earlier, []).append(step.position)
            else:
                consumer[earlier] = step.position
    return consumer, [
        t("grid.step_again", step=earlier, steps=_steps(positions))
        for earlier, positions in sorted(shared.items())
    ]


def build(steps: list[Step], ingredients: list[Ingredient]) -> Grid:
    if not ingredients:
        return Grid()

    owner, repeated = _first_use(steps)
    consumer, shared = _first_consumer(steps)
    children: dict[int, list[int]] = {}
    for earlier, into in consumer.items():
        children.setdefault(into, []).append(earlier)

    mine: dict[int, list[int]] = {}
    for ingredient, step in owner.items():
        mine.setdefault(step, []).append(ingredient)

    covers: dict[int, list[int]] = {}
    column: dict[int, int] = {}
    for step in sorted(steps, key=lambda one: one.position):
        kids = sorted(children.get(step.position, []), key=lambda one: (-column[one], one))
        rows_under: list[int] = []
        for child in kids:
            rows_under.extend(covers[child])
        rows_under.extend(sorted(mine.get(step.position, [])))
        covers[step.position] = rows_under
        column[step.position] = 1 + max((column[one] for one in kids if covers[one]), default=0)

    roots = sorted(one.position for one in steps if one.position not in consumer)

    order: list[int] = []
    for root in roots:
        order.extend(covers[root])

    orphans = [one.position for one in ingredients if one.position not in owner]
    named = {one.position: one.name for one in ingredients}
    rows = [Row(position=p, name=named.get(p, "?")) for p in order if p in named]
    rows += [Row(position=p, name=named[p], orphan=True) for p in orphans]
    at = {row.position: index + 1 for index, row in enumerate(rows)}

    cells: list[Cell] = []
    bands: list[Band] = []
    for step in sorted(steps, key=lambda one: one.position):
        covered = [p for p in covers[step.position] if p in at]
        if not covered:
            bands.append(
                Band(
                    position=step.position,
                    action=step.action,
                    text=step.text,
                    minutes=step.minutes,
                    attended=step.attended,
                    equipment=step.equipment,
                )
            )
            continue
        cells.append(
            Cell(
                position=step.position,
                action=step.action,
                text=step.text,
                minutes=step.minutes,
                attended=step.attended,
                equipment=step.equipment,
                column=column[step.position],
                row=at[covered[0]],
                span=len(covered),
            )
        )

    notes = list(repeated) + list(shared)
    if steps and not cells:
        notes.append(t("grid.no_uses"))
    if orphans:
        names = ", ".join(named[p] for p in orphans)
        notes.append(t("grid.orphans", names=names))

    return Grid(
        rows=tuple(rows),
        cells=tuple(cells),
        bands=tuple(bands),
        columns=max((cell.column for cell in cells), default=0),
        notes=tuple(notes),
    )
