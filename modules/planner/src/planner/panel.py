from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from planner import widgets


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Planner aún no tiene nada que contar")


def upcoming(entries: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    out = []
    for entry in entries:
        if entry.get("all_day") or len(entry.get("start", "")) <= 10:
            continue
        try:
            start = datetime.fromisoformat(entry["start"])
        except ValueError:
            continue
        if start.tzinfo is None or start >= now.astimezone(start.tzinfo):
            out.append({**entry, "_start": start})
    return sorted(out, key=lambda one: one["_start"])


def month_block(envelope: dict[str, Any] | None, now: datetime) -> dict[str, Any] | None:
    if (envelope or {}).get("state") != "ready":
        return None
    body = ready(envelope)
    local = now.astimezone(ZoneInfo(widgets.HOME_TZ))
    entries = []
    for one in (body.get("entries") or [])[:300]:
        if not one.get("start") or not one.get("title"):
            continue
        entry = {"start": one["start"], "title": str(one["title"])[:200]}
        if one.get("end"):
            entry["end"] = one["end"]
        if one.get("all_day"):
            entry["all_day"] = True
        if one.get("detail"):
            entry["detail"] = str(one["detail"])[:200]
        if one.get("tone"):
            entry["tone"] = one["tone"]
        entries.append(entry)
    return {
        "type": "month",
        "month": local.strftime("%Y-%m"),
        "today": local.day,
        "marked": [day for day in body.get("marked") or [] if 1 <= day <= 31],
        "entries": entries,
    }


def on_day(entries: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    return [
        one
        for one in entries
        if not one.get("all_day") and len(one.get("start", "")) > 10 and one["start"][:10] == day
    ]


async def build(connection: AsyncConnection) -> dict:
    found = await gather(connection, widgets.RENDERERS, ["today", "upnext", "calendar"])
    week = ready(found.get("today")).get("entries", [])
    now = datetime.now().astimezone()
    day = now.astimezone(ZoneInfo(widgets.HOME_TZ)).date()
    timed = on_day(week, day.isoformat())
    later = upcoming(timed, now)
    headlines = []
    if later:
        nxt = later[0]
        hour = nxt["_start"].strftime("%H:%M")
        headlines.append(
            {
                "text": f"La próxima, {nxt['title']} a las {hour}",
                "emphasis": f"{nxt['title']} a las {hour}",
                "status": f"{len(later)} {'cita' if len(later) == 1 else 'citas'}",
                "priority": 50,
            }
        )
    elif timed:
        headlines.append(
            {
                "text": "Ya no te queda nada más hoy",
                "status": "Libre",
                "tone": "positive",
                "priority": 20,
            }
        )
    elif week:
        headlines.append(
            {
                "text": "Hoy no tienes nada en el calendario",
                "status": "Libre",
                "tone": "positive",
                "priority": 20,
            }
        )
    blocks = blocks_of("agenda", found.get("today") or {}, label="Hoy", today=day)
    if not timed:
        blocks.insert(
            0, {"type": "alert", "tone": "neutral", "text": "Hoy no tienes nada en el calendario"}
        )
    if week:
        tiles = [
            {
                "label": "Hoy",
                "value": f"{len(timed)} {'cita' if len(timed) == 1 else 'citas'}"
                if timed
                else "Libre",
            }
        ]
        if later:
            tiles.append({"label": "La próxima", "value": later[0]["_start"].strftime("%H:%M")})
        tiles.append({"label": "La semana", "value": str(len(week))})
        blocks.insert(1, {"type": "tiles", "items": tiles})
    tabs = [
        {
            "id": "hoy",
            "label": "Agenda",
            "blocks": blocks,
            "actions": [{"label": "Abrir Planner", "href": "/planner/"}],
        }
    ]
    after = blocks_of("upnext", found.get("upnext") or {}, label="Lo próximo")
    if after:
        tabs.append(
            {
                "id": "proximo",
                "label": "Próximo",
                "blocks": after,
                "actions": [{"label": "La semana", "href": "/planner/"}],
            }
        )
    calendar = month_block(found.get("calendar"), now)
    if calendar:
        tabs.append(
            {
                "id": "mes",
                "label": "Mes",
                "blocks": [calendar],
                "actions": [{"label": "Abrir el mes", "href": "/planner/"}],
            }
        )
    questions = [
        {
            "text": "¿Qué tengo hoy?",
            "words": ["hoy", "agenda", "citas", "calendario", "reuniones"],
            "tab": "hoy",
        }
    ]
    if after:
        questions.append(
            {
                "text": "¿Qué tengo después?",
                "words": ["proximo", "siguiente", "semana", "manana"],
                "tab": "proximo",
            }
        )
    if calendar:
        questions.append(
            {
                "text": "¿Qué tengo este mes?",
                "words": ["mes", "calendario", "mensual"],
                "tab": "mes",
            }
        )
    return panel("day", order=10, headlines=headlines, tabs=tabs, questions=questions)
