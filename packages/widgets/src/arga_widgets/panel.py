from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Area = Literal["day", "money", "health", "work", "home", "leisure", "mind"]
Tone = Literal["positive", "warning", "negative", "neutral"]
Hue = Annotated[int, Field(ge=1, le=8)]
Text = Annotated[str, Field(min_length=1, max_length=200)]
Short = Annotated[str, Field(min_length=1, max_length=60)]
Href = Annotated[str, Field(pattern=r"^/[a-z0-9][a-z0-9/_?=&.%-]*$", max_length=300)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Headline(Strict):
    text: Text
    emphasis: str | None = None
    tone: Tone = "neutral"
    status: Short | None = None
    priority: Annotated[int, Field(ge=0, le=100)] = 50


class Block(Strict):
    detail: bool = False


class Figure(Block):
    type: Literal["figure"] = "figure"
    label: Short
    value: Short
    delta: Short | None = None
    tone: Tone = "neutral"
    foot: Text | None = None


class Point(Strict):
    label: Short
    value: float


class Trend(Block):
    type: Literal["trend"] = "trend"
    label: Short | None = None
    points: Annotated[list[Point], Field(min_length=2, max_length=400)]
    unit: Literal["money", "number", "kg", "percent", "hours"] = "number"


class Part(Strict):
    label: Short
    value: Short
    share: Annotated[float, Field(ge=0)]
    hue: Hue


class Split(Block):
    type: Literal["split"] = "split"
    label: Short | None = None
    total: Short | None = None
    parts: Annotated[list[Part], Field(min_length=1, max_length=8)]


class Tile(Strict):
    label: Short
    value: Short
    foot: Text | None = None
    tone: Tone = "neutral"
    series: Annotated[list[float], Field(max_length=60)] | None = None
    href: Href | None = None


class Tiles(Block):
    type: Literal["tiles"] = "tiles"
    items: Annotated[list[Tile], Field(min_length=1, max_length=8)]


class RingItem(Strict):
    label: Short
    value: Short
    share: Annotated[float, Field(ge=0)]
    hue: Hue


class Rings(Block):
    type: Literal["rings"] = "rings"
    items: Annotated[list[RingItem], Field(min_length=1, max_length=5)]


class Slot(Strict):
    start: str
    end: str
    title: Short
    hue: Hue = 1


class Timeline(Block):
    type: Literal["timeline"] = "timeline"
    items: Annotated[list[Slot], Field(max_length=30)]


class MonthEntry(Strict):
    start: str
    end: str | None = None
    title: Text
    all_day: bool = False
    detail: Text | None = None
    tone: Annotated[int, Field(ge=1, le=10)] | None = None


class Month(Block):
    type: Literal["month"] = "month"
    month: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    today: Annotated[int, Field(ge=1, le=31)] | None = None
    marked: Annotated[list[Annotated[int, Field(ge=1, le=31)]], Field(max_length=31)] = []
    entries: Annotated[list[MonthEntry], Field(max_length=300)] = []


class Task(Strict):
    id: Annotated[str, Field(min_length=1, max_length=200)]
    title: Text
    due: str | None = None
    overdue: bool = False
    done: bool = False
    hue: Hue | None = None


class Tasks(Block):
    type: Literal["tasks"] = "tasks"
    label: Short | None = None
    widget: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")]
    items: Annotated[list[Task], Field(max_length=20)]
    add: Short | None = None


class Row(Strict):
    label: Text
    value: Short
    tone: Tone = "neutral"
    href: Href | None = None


class Rows(Block):
    type: Literal["list"] = "list"
    label: Short | None = None
    rows: Annotated[list[Row], Field(max_length=12)]


class Alert(Block):
    type: Literal["alert"] = "alert"
    text: Text
    tone: Tone = "warning"
    href: Href | None = None


class Bars(Block):
    type: Literal["bars"] = "bars"
    label: Short | None = None
    labels: Annotated[list[Short], Field(min_length=1, max_length=31)]
    values: Annotated[list[float], Field(min_length=1, max_length=31)]
    highlight: int | None = None
    goal: float | None = None
    unit: Literal["money", "number", "kg", "percent", "hours"] = "number"


class Box(Strict):
    label: Short
    value: float
    hue: Hue


class Treemap(Block):
    type: Literal["treemap"] = "treemap"
    label: Short | None = None
    items: Annotated[list[Box], Field(min_length=1, max_length=12)]


class Feature(Block):
    type: Literal["feature"] = "feature"
    eyebrow: Short | None = None
    title: Text
    text: Text | None = None
    body: list[Literal["chest", "back", "shoulders", "arms", "core", "legs"]] | None = None
    action: Short | None = None
    href: Href | None = None


BLOCKS = (
    Figure,
    Trend,
    Split,
    Tiles,
    Rings,
    Timeline,
    Month,
    Tasks,
    Rows,
    Alert,
    Bars,
    Treemap,
    Feature,
)
AnyBlock = Annotated[
    Figure
    | Trend
    | Split
    | Tiles
    | Rings
    | Timeline
    | Month
    | Tasks
    | Rows
    | Alert
    | Bars
    | Treemap
    | Feature,
    Field(discriminator="type"),
]


class Action(Strict):
    label: Short
    href: Href
    primary: bool = False


class Tab(Strict):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,30}$")]
    label: Short
    blocks: Annotated[list[AnyBlock], Field(max_length=16)]
    actions: Annotated[list[Action], Field(max_length=4)] = []


class Question(Strict):
    text: Text
    words: Annotated[list[Short], Field(min_length=1, max_length=12)]
    tab: str
    block: Annotated[int, Field(ge=0)] = 0


class Panel(Strict):
    area: Area
    order: Annotated[int, Field(ge=0, le=100)] = 50
    headlines: Annotated[list[Headline], Field(max_length=6)] = []
    tabs: Annotated[list[Tab], Field(max_length=6)] = []
    questions: Annotated[list[Question], Field(max_length=20)] = []


class BadPanel(ValueError):
    pass


def panel(
    area: str,
    *,
    tabs: list[dict[str, Any]],
    headlines: list[dict[str, Any]] | None = None,
    questions: list[dict[str, Any]] | None = None,
    order: int = 50,
) -> dict[str, Any]:
    body = {
        "area": area,
        "order": order,
        "headlines": headlines or [],
        "tabs": tabs,
        "questions": questions or [],
    }
    try:
        checked = Panel.model_validate(body)
    except ValidationError as error:
        raise BadPanel(str(error)) from error
    ids = [tab.id for tab in checked.tabs]
    if len(ids) != len(set(ids)):
        raise BadPanel("dos pestañas con el mismo id")
    for question in checked.questions:
        if question.tab not in ids:
            raise BadPanel(f"la pregunta «{question.text}» apunta a una pestaña que no hay")
    return {
        "updated_at": datetime.now(UTC).isoformat(),
        **checked.model_dump(mode="json", exclude_none=True),
    }


def panels(*items: dict[str, Any]) -> dict[str, Any]:
    areas = [item["area"] for item in items]
    if len(areas) != len(set(areas)):
        raise BadPanel("dos paneles de la misma app en la misma área")
    return {"panels": list(items)}


def served(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = body.get("panels", [body])
    for item in items:
        panel(
            item["area"],
            tabs=item.get("tabs", []),
            headlines=item.get("headlines"),
            questions=item.get("questions"),
            order=item.get("order", 50),
        )
    return items


_MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _when(value: Any) -> str:
    text = str(value)
    try:
        day = date.fromisoformat(text[:10])
    except ValueError:
        return text[:60]
    return f"{day.day} {_MONTHS[day.month - 1]}"


def _number(value: Any, unit: str | None = None) -> str:
    if isinstance(value, int | float):
        rounded = round(value, 1) if abs(value) < 100 else round(value)
        text = f"{rounded:,}".replace(",", " ").replace(".", ",").replace(" ", ".")
        if isinstance(rounded, float) and text.endswith(",0"):
            text = text[:-2]
    else:
        text = str(value)
    return f"{text} {unit}".strip() if unit else text


def _hour(iso: str) -> str:
    return iso[11:16] if len(iso) >= 16 else ""


def blocks_of(
    kind: str,
    envelope: dict[str, Any],
    *,
    label: str | None = None,
    widget: str | None = None,
    hue: int = 1,
    today: date | None = None,
) -> list[dict[str, Any]]:
    if envelope.get("state") != "ready":
        return []
    body = envelope.get("body") or {}
    detail = body.get("detail")
    name = (label or "")[:60] or None
    if kind in ("kpi", "kpi-delta", "chart"):
        if body.get("value") is None:
            return []
        figure: dict[str, Any] = {
            "type": "figure",
            "label": name or "Hoy",
            "value": _number(body["value"], body.get("unit"))[:60],
        }
        previous = body.get("previous")
        if (
            kind == "kpi-delta"
            and isinstance(previous, int | float)
            and isinstance(body["value"], int | float)
            and previous
        ):
            change = body["value"] - previous
            good = body.get("good_when", "up")
            figure["delta"] = (
                f"{'+' if change > 0 else '−' if change < 0 else ''}"
                f"{_number(abs(change), body.get('unit'))} {body.get('since') or ''}"
            ).strip()[:60]
            figure["tone"] = (
                "neutral"
                if good == "neutral" or change == 0
                else "positive"
                if (change > 0) == (good == "up")
                else "warning"
            )
        if detail:
            figure["foot"] = str(detail)[:200]
        out = [figure]
        series = body.get("series")
        if series and len(series) >= 2:
            out.append(
                {
                    "type": "trend",
                    "points": [
                        {"label": str(i + 1), "value": float(v)} for i, v in enumerate(series)
                    ],
                    "label": name,
                }
            )
        return out
    if kind in ("progress", "ring"):
        value, target = body.get("value"), body.get("target")
        if value is None or not target:
            return []
        return [
            {
                "type": "rings",
                "items": [
                    {
                        "label": (body.get("label") or name or "Hoy")[:60],
                        "value": _number(value),
                        "share": max(0.0, float(value) / float(target)),
                        "hue": hue,
                    }
                ],
            }
        ]
    if kind == "bars":
        series = body.get("series") or []
        labels = body.get("labels") or [str(i + 1) for i in range(len(series))]
        if not series:
            return []
        return [
            {
                "type": "bars",
                "label": name,
                "labels": [str(one)[:60] for one in labels[:31]],
                "values": [float(v) for v in series[:31]],
                **({"highlight": body["highlight"]} if body.get("highlight") is not None else {}),
            }
        ]
    if kind == "stats":
        stats = body.get("stats") or []
        if not stats:
            return []
        return [
            {
                "type": "tiles",
                "items": [
                    {
                        "label": str(s["label"])[:60],
                        "value": _number(s["value"], s.get("unit"))[:60],
                    }
                    for s in stats[:8]
                ],
            }
        ]
    if kind == "list":
        rows = body.get("rows") or []
        if not rows:
            return []
        return [
            {
                "type": "list",
                "label": name,
                "rows": [
                    {
                        "label": str(r["label"])[:200],
                        "value": str(r["value"])[:60] or "·",
                        "tone": r.get("tone") or "neutral",
                    }
                    for r in rows[:12]
                ],
            }
        ]
    if kind == "upnext":
        events = body.get("events") or []
        if not events:
            return []
        return [
            {
                "type": "list",
                "label": name,
                "rows": [
                    {"label": str(e["title"])[:200], "value": (_hour(e["at"]) or e["at"][:10])[:60]}
                    for e in events[:8]
                ],
            }
        ]
    if kind in ("agenda", "week"):
        entries = [
            e
            for e in (body.get("entries") or [])
            if not e.get("all_day") and len(e.get("start", "")) > 10
        ]
        if not entries:
            return []
        first = today.isoformat() if today else entries[0]["start"][:10]
        items = [
            {
                "start": e["start"],
                "end": e.get("end") or e["start"],
                "title": str(e["title"])[:60],
                "hue": ((e.get("tone") or 1) - 1) % 8 + 1,
            }
            for e in entries
            if e["start"][:10] == first
        ][:20]
        later = [e for e in entries if e["start"][:10] > first]
        blocks = []
        if items:
            blocks = [
                {"type": "timeline", "items": items},
                {
                    "type": "list",
                    "label": name,
                    "rows": [{"label": i["title"], "value": _hour(i["start"])} for i in items[:6]],
                },
            ]
        if later:
            blocks.append(
                {
                    "type": "list",
                    "label": "Después",
                    "rows": [
                        {
                            "label": str(e["title"])[:60],
                            "value": f"{_when(e['start'])} · {_hour(e['start'])}",
                        }
                        for e in later[:4]
                    ],
                }
            )
        return blocks
    if kind == "tasks":
        tasks = body.get("tasks") or []
        if widget is None:
            return (
                [
                    {
                        "type": "list",
                        "label": name,
                        "rows": [
                            {
                                "label": str(t["title"])[:200],
                                "value": "hecho" if t.get("done") else "·",
                            }
                            for t in tasks[:12]
                        ],
                    }
                ]
                if tasks
                else []
            )
        return [
            {
                "type": "tasks",
                "label": name,
                "widget": widget,
                "items": [
                    {
                        "id": str(t["id"]),
                        "title": str(t["title"])[:200],
                        **(
                            {"due": _when(t.get("detail") or t.get("due"))}
                            if t.get("detail") or t.get("due")
                            else {}
                        ),
                        "overdue": bool(t.get("overdue")),
                        "done": bool(t.get("done")),
                        **({"hue": t["hue"]} if t.get("hue") else {}),
                    }
                    for t in tasks[:20]
                ],
                **({"add": "Añadir…"} if body.get("checkable") else {}),
            }
        ]
    return []


def tile_of(kind: str, envelope: dict[str, Any] | None, label: str) -> dict[str, Any] | None:
    if not envelope or envelope.get("state") != "ready":
        return None
    body = envelope.get("body") or {}
    value = body.get("value")
    if value is None:
        return None
    tile: dict[str, Any] = {"label": label[:60]}
    if kind in ("progress", "ring") and body.get("target"):
        tile["value"] = f"{_number(value)} de {_number(body['target'], body.get('unit'))}"[:60]
    else:
        tile["value"] = _number(value, body.get("unit"))[:60]
    figure = blocks_of("kpi-delta" if kind == "kpi-delta" else "kpi", envelope)
    if figure and figure[0].get("delta"):
        tile["foot"] = figure[0]["delta"][:200]
        tile["tone"] = figure[0].get("tone", "neutral")
    elif body.get("detail"):
        tile["foot"] = str(body["detail"])[:200]
    series = body.get("series")
    if series and len(series) >= 2:
        tile["series"] = [float(v) for v in series[-60:]]
    return tile


async def gather(
    connection: Any, renderers: dict[str, Any], ids: list[str]
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for widget_id in ids:
        renderer = renderers.get(widget_id)
        if renderer is None:
            continue
        try:
            async with connection.begin_nested():
                found[widget_id] = await renderer(connection)
        except Exception:  # noqa: BLE001 - un widget roto no puede dejar el inicio sin su área
            continue
    return found
