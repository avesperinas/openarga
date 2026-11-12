from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets import envelope
from notebook import markdown as md
from notebook import notes
from notebook.notes import MADRID

KINDS = {"recent": "list", "today": "list", "review": "list"}

ROWS = 6


def _ago(when: datetime) -> str:
    minutes = int((datetime.now(MADRID) - when).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    if minutes < 60 * 24:
        return f"{minutes // 60} h"
    return f"{minutes // (60 * 24)} d"


async def recent(connection: AsyncConnection) -> dict:
    since = datetime.combine(notes.today() - timedelta(days=30), time(), MADRID)
    found = await notes.recent(connection, since, None, None, ROWS, apps=False)
    if not found:
        return envelope(KINDS["recent"], "empty", {"detail": "nada cambiado este mes"})
    rows = [
        {
            "label": one.title,
            "value": ("Claude · " if one.updated_by == "tool" else "") + _ago(one.updated_at),
        }
        for one in found
    ]
    return envelope(KINDS["recent"], "ready", {"rows": rows})


async def today(connection: AsyncConnection) -> dict:
    found = await notes.daily(connection, None, False, "app")
    body = md.COMMENT.sub("", md.split(found.content).body) if found is not None else ""
    if not body.strip():
        return envelope(KINDS["today"], "empty", {"detail": "sin nota de hoy"})
    lines = [line.strip().lstrip("#-*> ").strip() for line in body.split("\n") if line.strip()]
    rows = [{"label": line[:80], "value": ""} for line in lines[:ROWS] if line]
    return envelope(KINDS["today"], "ready", {"rows": rows})


async def review(connection: AsyncConnection) -> dict:
    due = await notes.due_for_review(connection, ROWS)
    if due is None:
        return envelope(
            KINDS["review"],
            "empty",
            {"detail": "elige en Notebook qué propiedad dice cuándo repasar"},
        )
    if not due:
        return envelope(KINDS["review"], "empty", {"detail": "nada que repasar hoy"})
    today_ = notes.today()
    rows = []
    for one in due:
        late = (today_ - date.fromisoformat(one.due)).days
        rows.append({"label": one.title, "value": "hoy" if late <= 0 else f"hace {late} d"})
    return envelope(KINDS["review"], "ready", {"rows": rows})


RENDERERS = {"recent": recent, "today": today, "review": review}
