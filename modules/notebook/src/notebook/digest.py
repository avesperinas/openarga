from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_contracts import records as write
from notebook import markdown as md
from notebook import mirror, notes

MODULE = "notebook"
AUTHOR = "import"
APP_NAME = "Digest"
MADRID = ZoneInfo("Europe/Madrid")
FROM_HOUR = 6
METRIC = contracts.METRIC

Kind = Literal["week", "month", "quarter"]
FOLDERS: dict[Kind, str] = {
    "week": "Diario/Semanas",
    "month": "Diario/Meses",
    "quarter": "Diario/Trimestres",
}
MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
QUESTIONS = ("¿Sigue importando?", "¿Qué la frenó?", "¿Qué cambias?")


@dataclass(frozen=True)
class Period:
    kind: Kind
    start: date
    end: date

    @property
    def title(self) -> str:
        if self.kind == "week":
            year, week, _ = self.start.isocalendar()
            return f"{year}-W{week:02d}"
        if self.kind == "month":
            return f"{self.start.year}-{self.start.month:02d}"
        return f"{self.start.year}-T{(self.start.month - 1) // 3 + 1}"

    @property
    def folder(self) -> str:
        return FOLDERS[self.kind]

    @property
    def path(self) -> str:
        return f"{self.folder}/{self.title}"

    def previous(self) -> Period:
        return of(self.kind, self.start - timedelta(days=1))

    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]


def of(kind: Kind, day: date) -> Period:
    if kind == "week":
        start = day - timedelta(days=day.weekday())
        return Period(kind, start, start + timedelta(days=6))
    if kind == "month":
        start = day.replace(day=1)
        following = (start + timedelta(days=32)).replace(day=1)
        return Period(kind, start, following - timedelta(days=1))
    first_month = (day.month - 1) // 3 * 3 + 1
    start = date(day.year, first_month, 1)
    after = first_month + 3
    following = date(day.year + 1, 1, 1) if after > 12 else date(day.year, after, 1)
    return Period(kind, start, following - timedelta(days=1))


def parse(ref: str) -> Period:
    clean = ref.strip().upper()
    if "-W" in clean:
        year, week = clean.split("-W")
        return of("week", date.fromisocalendar(int(year), int(week), 1))
    if "-T" in clean:
        year, quarter = clean.split("-T")
        if not 1 <= int(quarter) <= 4:
            raise ValueError(ref)
        return of("quarter", date(int(year), (int(quarter) - 1) * 3 + 1, 1))
    year, month = clean.split("-")
    return of("month", date(int(year), int(month), 1))


def due(now: datetime) -> list[Period]:
    local = now.astimezone(MADRID)
    today = local.date() if local.hour >= FROM_HOUR else local.date() - timedelta(days=1)
    this_week = of("week", today)
    last_week = this_week.previous()
    this_month = of("month", today)
    last_month = this_month.previous()
    return [
        last_week.previous(),
        last_week,
        last_month.previous(),
        last_month,
        of("quarter", today),
    ]


POINTS = text(f"""
    select distinct on (payload->'{METRIC}'->>'key', payload->'{METRIC}'->>'day')
        module,
        payload->'{METRIC}'->>'key' as key,
        (payload->'{METRIC}'->>'day')::date as day,
        (payload->'{METRIC}'->>'value')::float8 as value,
        payload->'{METRIC}'->>'label' as label,
        payload->'{METRIC}'->>'unit' as unit,
        payload->'{METRIC}'->>'kind' as kind
    from notebook.events
    where payload ? '{METRIC}'
      and (payload->'{METRIC}'->>'day')::date between :since and :until
    order by payload->'{METRIC}'->>'key', payload->'{METRIC}'->>'day', ts desc, ingested_at desc
""")

CHANGED = text("""
    select app, app_name, record_id, title, kind
    from notebook.notebook_record
    where day is null and not removed and kind <> 'Meta' and not properties ? 'semana'
      and seen_at >= :since and seen_at < :until
    order by app_name, kind, title
""")

TOLD = text("""
    select app, app_name, record_id, body
    from notebook.notebook_record
    where day is null and not removed and properties ->> 'semana' = :week
    order by app_name, app
""")

GOALS = text("""
    select app, record_id, title, properties
    from notebook.notebook_record
    where kind = 'Meta' and not removed
    order by title
""")

NAMES = text("select distinct on (app) app, app_name from notebook.notebook_record order by app")


@dataclass
class Figure:
    key: str
    app: str
    label: str
    unit: str
    kind: str
    points: dict[date, float] = field(default_factory=dict)

    def over(self, period: Period) -> float | None:
        inside = sorted((d, v) for d, v in self.points.items() if period.start <= d <= period.end)
        if not inside:
            return None
        if self.kind == "amount":
            return sum(v for _, v in inside)
        if self.kind == "peak":
            return max(v for _, v in inside)
        return inside[-1][1]


async def figures(connection: AsyncConnection, since: date, until: date) -> list[Figure]:
    found: dict[str, Figure] = {}
    for row in await connection.execute(POINTS, {"since": since, "until": until}):
        if not row.key or row.value is None or row.module == MODULE:
            continue
        one = found.get(row.key)
        if one is None:
            kind = row.kind if row.kind in ("amount", "peak") else "level"
            one = found[row.key] = Figure(
                row.key, row.module, row.label or row.key, row.unit or "", kind
            )
        one.label = row.label or one.label
        one.points[row.day] = float(row.value)
    return list(found.values())


UNITS = {"EUR": "€", "percent": "%", "steps": "pasos", "count": "", "points": ""}


def said(value: float, unit: str) -> str:
    shown = write.trimmed(round(value, 2) if abs(value) < 100 else round(value))
    suffix = UNITS.get(unit, unit)
    return f"{shown} {suffix}".strip()


def change(now: float | None, before: float | None, unit: str) -> str:
    if now is None or before is None:
        return ""
    diff = now - before
    if abs(diff) < 1e-9:
        return "="
    sign = "+" if diff > 0 else "−"
    relative = f" ({sign}{abs(diff) / abs(before):.0%})" if before else ""
    return f"{sign}{said(abs(diff), unit)}{relative}"


def long_period(period: Period) -> str:
    if period.kind == "week":
        return f"del {write.long_date(period.start)} al {write.long_date(period.end)}"
    if period.kind == "month":
        return f"{MONTHS[period.start.month - 1]} de {period.start.year}"
    return f"el {period.title[-2:]} de {period.start.year}"


def link(app: str, record_id: str, title: str) -> str:
    return f"[[{app}:{record_id}|{md.safe_title(title)}]]"


def figures_section(found: list[Figure], period: Period, names: dict[str, str]) -> str:
    before = period.previous()
    by_app: dict[str, list[str]] = {}
    for one in sorted(
        found, key=lambda f: (names.get(f.app, f.app).casefold(), f.label.casefold())
    ):
        now = one.over(period)
        if now is None:
            continue
        then = one.over(before)
        by_app.setdefault(names.get(one.app, one.app.capitalize()), []).append(
            [
                one.label,
                said(now, one.unit),
                said(then, one.unit) if then is not None else "",
                change(now, then, one.unit),
            ]
        )
    if not by_app:
        return "## Cifras\n\nNinguna app publicó cifras en este periodo."
    word = {"week": "La anterior", "month": "El anterior", "quarter": "El anterior"}[period.kind]
    parts = ["## Cifras"]
    for app, rows in by_app.items():
        parts.append(f"### {app}\n\n" + write.table(["Cifra", "Ahora", word, "Cambio"], rows))
    return "\n\n".join(parts)


def told_section(rows: list[Any]) -> str:
    parts = []
    for row in rows:
        text_ = "\n".join(
            f"#{line}" if line.startswith("#") else line for line in row.body.strip().split("\n")
        )
        parts.append(f"{text_}\n\nLo cuenta {link(row.app, row.record_id, row.app_name)}.")
    return "## La semana contada\n\n" + "\n\n".join(parts) if parts else ""


def happened_section(rows: list[Any]) -> str:
    if not rows:
        return ""
    by_app: dict[str, list[str]] = {}
    for row in rows:
        by_app.setdefault(row.app_name, []).append(link(row.app, row.record_id, row.title))
    lines = [f"- **{app}**: " + ", ".join(items) for app, items in by_app.items()]
    return "## Lo que pasó\n\n" + "\n".join(lines)


def _when(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def goals_section(rows: list[Any], period: Period) -> str:
    achieved, missed, behind = [], [], []
    for row in rows:
        props = row.properties or {}
        closed = _when(props.get("cerrada"))
        name = link(row.app, row.record_id, row.title)
        if props.get("estado") == "lograda" and closed and period.start <= closed <= period.end:
            achieved.append(name)
        elif props.get("estado") == "fallida" and closed and period.start <= closed <= period.end:
            missed.append(name)
        elif props.get("estado") == "activa" and props.get("ritmo") == "por detrás":
            behind.append(name)
    lines = []
    for label, items in (("Cumplidas", achieved), ("En riesgo", behind), ("Fallidas", missed)):
        if items:
            lines.append(f"- **{label}**: " + ", ".join(items))
    return "## Metas\n\n" + "\n".join(lines) if lines else ""


def days_section(period: Period) -> str:
    if period.kind == "week":
        return "## Días\n\n" + " · ".join(f"[[{d.isoformat()}]]" for d in period.days())
    weeks: list[str] = []
    for d in period.days():
        title = of("week", d).title
        if title not in weeks:
            weeks.append(title)
    return "## Semanas\n\n" + " · ".join(f"[[{w}]]" for w in weeks)


def block(
    period: Period,
    found: list[Figure],
    happened: list[Any],
    goals: list[Any],
    names: dict[str, str],
    told: list[Any] | None = None,
) -> str:
    head = f"Cómo fue {long_period(period)}, con las cifras de cada app y lo que pasó."
    sections = [
        told_section(told or []),
        head,
        figures_section(found, period, names),
        happened_section(happened),
        goals_section(goals, period),
        days_section(period),
    ]
    return "\n\n".join(one for one in sections if one)


def _goal_line(props: dict[str, Any]) -> str:
    unit = props.get("unidad")
    parts = []
    if props.get("actual") is not None:
        current = f"{write.trimmed(props['actual'])} {unit or ''}".strip()
        target = props.get("objetivo")
        parts.append(
            f"ahora {current}"
            + (f" de {write.trimmed(target)} {unit or ''}".rstrip() if target is not None else "")
        )
    if props.get("progreso") is not None:
        parts.append(f"{props['progreso']} % hecho")
    if props.get("ritmo"):
        parts.append(str(props["ritmo"]))
    if props.get("esperado") is not None:
        parts.append(f"a estas alturas pedía {write.trimmed(props['esperado'])}")
    if props.get("hasta"):
        parts.append(f"hasta el {props['hasta']}")
    return " · ".join(parts) if parts else "sin cifra"


def quarter_block(period: Period, goals: list[Any]) -> str:
    active = [row for row in goals if (row.properties or {}).get("estado") == "activa"]
    head = f"La revisión de metas al empezar {long_period(period)}."
    if not active:
        return head + "\n\nNo hay metas abiertas."
    lines = [head, ""]
    for row in active:
        lines.append(
            f"- {link(row.app, row.record_id, row.title)}: {_goal_line(row.properties or {})}"
        )
    return "\n".join(lines)


def quarter_questions(goals: list[Any]) -> str:
    active = [row for row in goals if (row.properties or {}).get("estado") == "activa"]
    parts = []
    for row in active:
        questions = "\n".join(f"- {one} " for one in QUESTIONS)
        parts.append(f"## {md.safe_title(row.title)}\n\n{questions}")
    return "\n\n".join(parts)


async def compose(
    connection: AsyncConnection,
    period: Period,
    names: dict[str, str] | None = None,
) -> str:
    goals = (await connection.execute(GOALS)).all()
    if period.kind == "quarter":
        return quarter_block(period, goals)
    if names is None:
        names = {row.app: row.app_name for row in await connection.execute(NAMES)}
    before = period.previous()
    found = await figures(connection, before.start, period.end)
    since = datetime.combine(period.start, time.min, MADRID)
    until = datetime.combine(period.end + timedelta(days=1), time.min, MADRID)
    happened = (await connection.execute(CHANGED, {"since": since, "until": until})).all()
    told = (
        (await connection.execute(TOLD, {"week": period.title})).all()
        if period.kind == "week"
        else []
    )
    return block(period, found, happened, goals, names, told)


async def _note(connection: AsyncConnection, period: Period) -> Any:
    try:
        return await notes.find_row(connection, period.path)
    except notes.NotFound:
        return None


async def write_period(connection: AsyncConnection, period: Period, names: dict[str, str]) -> str:
    current = await _note(connection, period)
    if current is not None and period.kind == "quarter":
        return "kept"
    wanted = await compose(connection, period, names)
    if current is None:
        trashed = (
            await connection.execute(
                text(
                    "select 1 from notebook.notebook_note where deleted_at is not null "
                    "and folder_key = :folder and title_key = :title"
                ),
                {"folder": md.key(md.folder(period.folder)), "title": md.key(period.title)},
            )
        ).first()
        if trashed:
            return "kept"
        content = md.with_block("", wanted)
        if period.kind == "quarter":
            questions = quarter_questions((await connection.execute(GOALS)).all())
            content = content + ("\n" + questions + "\n" if questions else "")
        await notes.ensure_folder(connection, period.folder)
        await notes.create(connection, period.folder, period.title, content, AUTHOR, APP_NAME)
        return "written"
    found = md.block(current.content)
    if found is not None and found.inner == wanted:
        return "same"
    content = md.with_block(current.content, wanted)
    await notes._save(connection, current, content, AUTHOR, app=APP_NAME)
    return "written"


async def refresh(
    connection: AsyncConnection,
    now: datetime | None = None,
    names: Callable[[], Awaitable[dict[str, str]]] = mirror.app_names,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    known = {row.app: row.app_name for row in await connection.execute(NAMES)}
    looked_up: dict[str, str] | None = None
    done: dict[str, int] = {}
    for period in due(now):
        if period.kind != "quarter":
            wanted_apps = {f.app for f in await figures(connection, period.start, period.end)}
            if wanted_apps - set(known) and looked_up is None:
                looked_up = await names()
                known = {**looked_up, **known}
        try:
            async with connection.begin_nested():
                outcome = await write_period(connection, period, known)
        except Exception as error:  # noqa: BLE001 - un periodo que falla no para los demás
            print(f"digest · {period.path}: {type(error).__name__}: {error}", file=sys.stderr)
            outcome = "failed"
        done[outcome] = done.get(outcome, 0) + 1
    return done


async def notifications(
    connection: AsyncConnection, now: datetime | None = None
) -> list[dict[str, Any]]:
    from arga_contracts import notify

    now = now or datetime.now(UTC)
    local = now.astimezone(MADRID)
    week = of("week", local.date()).previous()
    when = datetime.combine(week.end + timedelta(days=1), time(FROM_HOUR), MADRID)
    if now < when or now - when > timedelta(days=2):
        return []
    found = await _note(connection, week)
    if found is None:
        return []
    return [
        notify.notification(
            "week",
            f"week:{week.title}",
            "Tu semana",
            f"/notebook/nota/{found.id}",
            when,
            f"Cómo fue {long_period(week)}",
        )
    ]
