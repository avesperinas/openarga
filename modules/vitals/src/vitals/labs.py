from __future__ import annotations

import json
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from vitals.weight import Conflict, NotFound

PDF_LIMIT = 20 * 1024 * 1024


def plain(raw: str) -> str:
    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return " ".join(folded.replace("*", " ").lower().split())


def unit_key(raw: str | None) -> str:
    if not raw:
        return ""
    unit = raw.replace("µ", "u").replace("μ", "u").replace("³", "^3").replace("⁶", "^6")
    unit = "".join(unit.lower().split()).lstrip("·")
    unit = unit.removeprefix("x").replace("mill/", "10^6/")
    return "u/l" if unit in ("u/i", "ui/l") else unit


def out_of_range(value: float | None, low: float | None, high: float | None) -> bool:
    if value is None:
        return False
    return (low is not None and value < low) or (high is not None and value > high)


def _num(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


class Analyte(BaseModel):
    id: str
    name: str
    panel: str
    unit: str | None
    about: str


CATALOGUE = text("""
    select id, name, panel, unit, conversions, aliases, about
    from vitals.vitals_analyte order by position
""")


async def catalogue(connection: AsyncConnection) -> list[Analyte]:
    rows = (await connection.execute(CATALOGUE)).all()
    return [Analyte(id=r.id, name=r.name, panel=r.panel, unit=r.unit, about=r.about) for r in rows]


async def find(connection: AsyncConnection, wanted: str) -> Any:
    key = plain(wanted)
    rows = (await connection.execute(CATALOGUE)).all()
    for row in rows:
        if key in (row.id, plain(row.name), *(plain(alias) for alias in row.aliases)):
            return row
    known = ", ".join(row.id for row in rows)
    raise NotFound(f"el analito '{wanted}'; los que hay: {known}")


def canonical(row: Any, value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    if not unit or not row.unit or unit_key(unit) == unit_key(row.unit):
        return value
    for other, factor in (row.conversions or {}).items():
        if unit_key(other) == unit_key(unit):
            return round(value * float(factor), 4)
    return None


class CheckupIn(BaseModel):
    day: date
    center: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class Checkup(BaseModel):
    id: str
    day: date
    center: str | None
    notes: str | None
    values: int
    out: int
    document: str | None


FIND_CHECKUP = text("""
    select id from vitals.vitals_checkup
    where day = :day and coalesce(center, '') = coalesce(:center, '')
""")
INSERT_CHECKUP = text("""
    insert into vitals.vitals_checkup (day, center, notes) values (:day, :center, :notes)
    on conflict do nothing
    returning id
""")


async def record_checkup(connection: AsyncConnection, wanted: CheckupIn) -> tuple[str, bool]:
    values = {
        "day": wanted.day,
        "center": (wanted.center or "").strip() or None,
        "notes": (wanted.notes or "").strip() or None,
    }
    created = await connection.scalar(INSERT_CHECKUP, values)
    if created is not None:
        return str(created), False
    return str(await connection.scalar(FIND_CHECKUP, values)), True


CHECKUPS = text("""
    select c.id, c.day, c.center, c.notes, d.filename as document,
           count(r.id) as values,
           count(r.id) filter (where r.value < r.ref_low or r.value > r.ref_high) as out
    from vitals.vitals_checkup c
    left join vitals.vitals_lab_result r on r.checkup_id = c.id
    left join vitals.vitals_checkup_document d on d.checkup_id = c.id
    group by c.id, d.filename
    order by c.day desc
""")


async def checkups(connection: AsyncConnection) -> list[Checkup]:
    return [
        Checkup(
            id=str(row.id),
            day=row.day,
            center=row.center,
            notes=row.notes,
            values=row.values,
            out=row.out,
            document=row.document,
        )
        for row in (await connection.execute(CHECKUPS)).all()
    ]


EXISTS = text("select 1 from vitals.vitals_checkup where id = cast(:id as uuid)")


async def _checkup_exists(connection: AsyncConnection, checkup_id: str) -> None:
    if not await connection.scalar(EXISTS, {"id": checkup_id}):
        raise NotFound(f"la revisión {checkup_id}")


class ResultIn(BaseModel):
    analyte: str = Field(min_length=1, max_length=80)
    value: float | None = None
    value_text: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=30)
    ref_low: float | None = None
    ref_high: float | None = None

    @model_validator(mode="after")
    def _something(self) -> ResultIn:
        if self.value is None and not (self.value_text or "").strip():
            raise ValueError("hace falta un valor, en número o en texto")
        if self.ref_low is not None and self.ref_high is not None and self.ref_low > self.ref_high:
            raise ValueError("el rango está al revés")
        return self


class Result(BaseModel):
    analyte: str
    name: str
    value: float | None
    value_text: str | None
    unit: str | None
    ref_low: float | None
    ref_high: float | None
    out: bool
    replaced: bool = False


UPSERT = text("""
    insert into vitals.vitals_lab_result
        (checkup_id, analyte_id, value, value_text, unit, ref_low, ref_high)
    values (cast(:checkup as uuid), :analyte, :value, :value_text, :unit, :ref_low, :ref_high)
    on conflict (checkup_id, analyte_id) do update set
        value = excluded.value, value_text = excluded.value_text, unit = excluded.unit,
        ref_low = excluded.ref_low, ref_high = excluded.ref_high
    returning id, (xmax <> 0) as replaced
""")

ENQUEUE = text("""
    insert into vitals.vitals_outbox (type, payload, dedup_hash)
    values ('vitals.lab_result', cast(:payload as jsonb), :dedup)
    on conflict do nothing
""")

DAY_OF = text("select day from vitals.vitals_checkup where id = cast(:id as uuid)")


async def add_result(connection: AsyncConnection, checkup_id: str, wanted: ResultIn) -> Result:
    await _checkup_exists(connection, checkup_id)
    analyte = await find(connection, wanted.analyte)
    values = {
        "checkup": checkup_id,
        "analyte": analyte.id,
        "value": None if wanted.value is None else Decimal(str(wanted.value)),
        "value_text": (wanted.value_text or "").strip() or None,
        "unit": (wanted.unit or "").strip() or None,
        "ref_low": None if wanted.ref_low is None else Decimal(str(wanted.ref_low)),
        "ref_high": None if wanted.ref_high is None else Decimal(str(wanted.ref_high)),
    }
    row = (await connection.execute(UPSERT, values)).one()
    out = out_of_range(wanted.value, wanted.ref_low, wanted.ref_high)
    day = await connection.scalar(DAY_OF, {"id": checkup_id})
    await connection.execute(
        ENQUEUE,
        {
            "payload": json.dumps(
                {
                    "checkup_id": checkup_id,
                    "day": day.isoformat(),
                    "analyte": analyte.id,
                    "value": wanted.value,
                    "value_text": values["value_text"],
                    "unit": values["unit"],
                    "ref_low": wanted.ref_low,
                    "ref_high": wanted.ref_high,
                    "out_of_range": out,
                }
            ),
            "dedup": f"lab:{row.id}:{wanted.value}:{values['value_text']}:{values['unit']}",
        },
    )
    return Result(
        analyte=analyte.id,
        name=analyte.name,
        value=wanted.value,
        value_text=values["value_text"],
        unit=values["unit"],
        ref_low=wanted.ref_low,
        ref_high=wanted.ref_high,
        out=out,
        replaced=row.replaced,
    )


class Cell(BaseModel):
    value: float | None
    value_text: str | None
    unit: str | None
    ref_low: float | None
    ref_high: float | None
    out: bool


class Row(BaseModel):
    analyte: Analyte
    cells: dict[str, Cell]


class Table(BaseModel):
    checkups: list[Checkup]
    rows: list[Row]


RESULTS = text("""
    select r.checkup_id, r.analyte_id, r.value, r.value_text, r.unit, r.ref_low, r.ref_high
    from vitals.vitals_lab_result r
""")


async def table(connection: AsyncConnection) -> Table:
    found = await checkups(connection)
    cells: dict[str, dict[str, Cell]] = {}
    for row in (await connection.execute(RESULTS)).all():
        value = _num(row.value)
        low, high = _num(row.ref_low), _num(row.ref_high)
        cells.setdefault(row.analyte_id, {})[str(row.checkup_id)] = Cell(
            value=value,
            value_text=row.value_text,
            unit=row.unit,
            ref_low=low,
            ref_high=high,
            out=out_of_range(value, low, high),
        )
    return Table(
        checkups=found,
        rows=[
            Row(analyte=one, cells=cells[one.id])
            for one in await catalogue(connection)
            if one.id in cells
        ],
    )


class Point(BaseModel):
    day: date
    checkup_id: str
    value: float
    ref_low: float | None
    ref_high: float | None
    out: bool


class Evolution(BaseModel):
    analyte: Analyte
    points: list[Point]
    skipped: int


EVOLUTION = text("""
    select c.id as checkup_id, c.day, r.value, r.unit, r.ref_low, r.ref_high
    from vitals.vitals_lab_result r
    join vitals.vitals_checkup c on c.id = r.checkup_id
    where r.analyte_id = :analyte and r.value is not null
    order by c.day, c.created_at, c.id
""")


EVOLUTIONS = text("""
    select r.analyte_id, c.id as checkup_id, c.day, r.value, r.unit, r.ref_low, r.ref_high
    from vitals.vitals_lab_result r
    join vitals.vitals_checkup c on c.id = r.checkup_id
    where r.value is not null
    order by c.day, c.created_at, c.id
""")


async def evolution(connection: AsyncConnection, wanted: str) -> Evolution:
    analyte = await find(connection, wanted)
    rows = (await connection.execute(EVOLUTION, {"analyte": analyte.id})).all()
    return _evolution(analyte, rows)


async def evolutions(connection: AsyncConnection) -> list[Evolution]:
    by_analyte: dict[str, list[Any]] = {}
    for row in (await connection.execute(EVOLUTIONS)).all():
        by_analyte.setdefault(row.analyte_id, []).append(row)
    return [
        _evolution(analyte, by_analyte.get(analyte.id, []))
        for analyte in (await connection.execute(CATALOGUE)).all()
    ]


def _evolution(analyte: Any, rows: list[Any]) -> Evolution:
    points: list[Point] = []
    skipped = 0
    for row in rows:
        value = canonical(analyte, _num(row.value), row.unit)
        if value is None:
            skipped += 1
            continue
        low = canonical(analyte, _num(row.ref_low), row.unit)
        high = canonical(analyte, _num(row.ref_high), row.unit)
        points.append(
            Point(
                day=row.day,
                checkup_id=str(row.checkup_id),
                value=value,
                ref_low=low,
                ref_high=high,
                out=out_of_range(value, low, high),
            )
        )
    return Evolution(
        analyte=Analyte(
            id=analyte.id,
            name=analyte.name,
            panel=analyte.panel,
            unit=analyte.unit,
            about=analyte.about,
        ),
        points=points,
        skipped=skipped,
    )


SAVE_DOCUMENT = text("""
    insert into vitals.vitals_checkup_document (checkup_id, filename, size, content)
    values (cast(:checkup as uuid), :filename, :size, :content)
    on conflict (checkup_id) do update set
        filename = excluded.filename, size = excluded.size, content = excluded.content,
        uploaded_at = now()
""")

READ_DOCUMENT = text("""
    select filename, content from vitals.vitals_checkup_document where checkup_id = cast(:id as uuid)
""")


async def save_document(
    connection: AsyncConnection, checkup_id: str, filename: str, content: bytes
) -> None:
    await _checkup_exists(connection, checkup_id)
    if len(content) > PDF_LIMIT:
        raise Conflict("el PDF pasa de 20 MB")
    if not content.startswith(b"%PDF-"):
        raise Conflict("eso no es un PDF")
    name = (filename or "").strip()[:200] or "revision.pdf"
    await connection.execute(
        SAVE_DOCUMENT,
        {"checkup": checkup_id, "filename": name, "size": len(content), "content": content},
    )


async def document(connection: AsyncConnection, checkup_id: str) -> tuple[str, bytes]:
    row = (await connection.execute(READ_DOCUMENT, {"id": checkup_id})).one_or_none()
    if row is None:
        raise NotFound(f"el PDF de la revisión {checkup_id}")
    return row.filename, bytes(row.content)


class Latest(BaseModel):
    analyte: str
    day: date
    value: float
    unit: str | None
    ref_low: float | None
    ref_high: float | None
    out: bool
    previous: float | None
    previous_day: date | None


async def latest(connection: AsyncConnection, analyte: str = "ldl") -> Latest | None:
    found = await evolution(connection, analyte)
    if not found.points:
        return None
    last = found.points[-1]
    before = found.points[-2] if len(found.points) > 1 else None
    return Latest(
        analyte=found.analyte.id,
        day=last.day,
        value=last.value,
        unit=found.analyte.unit,
        ref_low=last.ref_low,
        ref_high=last.ref_high,
        out=last.out,
        previous=before.value if before else None,
        previous_day=before.day if before else None,
    )


class Change(BaseModel):
    analyte: Analyte
    value: float
    previous: float
    unit: str | None
    change: float
    out: bool
    was_out: bool


class Changes(BaseModel):
    checkup: Checkup | None
    previous: Checkup | None
    changes: list[Change]


async def changes(connection: AsyncConnection) -> Changes:
    found = await table(connection)
    if len(found.checkups) < 2:
        return Changes(
            checkup=found.checkups[0] if found.checkups else None, previous=None, changes=[]
        )
    last, before = found.checkups[0], found.checkups[1]
    out = []
    for row in found.rows:
        now, then = row.cells.get(last.id), row.cells.get(before.id)
        if not now or not then or now.value is None or then.value is None:
            continue
        if unit_key(now.unit) != unit_key(then.unit):
            continue
        out.append(
            Change(
                analyte=row.analyte,
                value=now.value,
                previous=then.value,
                unit=now.unit,
                change=round(now.value - then.value, 3),
                out=now.out,
                was_out=then.out,
            )
        )
    out.sort(
        key=lambda one: (
            one.out == one.was_out,
            -abs(one.change) / (abs(one.previous) or 1),
        )
    )
    return Changes(checkup=last, previous=before, changes=out)
