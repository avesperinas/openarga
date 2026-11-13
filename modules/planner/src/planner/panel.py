from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_widgets.panel import blocks_of, gather, panel
from planner import widgets, zones
from planner.words import say, words


def ready(envelope: dict[str, Any] | None) -> dict[str, Any]:
    return (envelope or {}).get("body") or {} if (envelope or {}).get("state") == "ready" else {}


def nothing() -> HTTPException:
    return HTTPException(status_code=404, detail="Planner has nothing to tell yet")


def _events(count: int) -> str:
    return say("panel.events.one" if count == 1 else "panel.events.other", count=count)


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
    local = now.astimezone(zones.home())
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
    day = now.astimezone(zones.home()).date()
    timed = on_day(week, day.isoformat())
    later = upcoming(timed, now)
    headlines = []
    if later:
        nxt = later[0]
        hour = nxt["_start"].strftime("%H:%M")
        headlines.append(
            {
                "text": say("panel.next", title=nxt["title"], hour=hour),
                "emphasis": say("panel.next.emphasis", title=nxt["title"], hour=hour),
                "status": _events(len(later)),
                "priority": 50,
            }
        )
    elif timed:
        headlines.append(
            {
                "text": say("panel.nothing_left"),
                "status": say("panel.free"),
                "tone": "positive",
                "priority": 20,
            }
        )
    elif week:
        headlines.append(
            {
                "text": say("panel.nothing_today"),
                "status": say("panel.free"),
                "tone": "positive",
                "priority": 20,
            }
        )
    blocks = blocks_of("agenda", found.get("today") or {}, label=say("panel.today"), today=day)
    if not timed:
        blocks.insert(0, {"type": "alert", "tone": "neutral", "text": say("panel.nothing_today")})
    if week:
        tiles = [
            {
                "label": say("panel.today"),
                "value": _events(len(timed)) if timed else say("panel.free"),
            }
        ]
        if later:
            tiles.append(
                {"label": say("panel.next_tile"), "value": later[0]["_start"].strftime("%H:%M")}
            )
        tiles.append({"label": say("panel.week"), "value": str(len(week))})
        blocks.insert(1, {"type": "tiles", "items": tiles})
    tabs = [
        {
            "id": "today",
            "label": say("panel.agenda"),
            "blocks": blocks,
            "actions": [{"label": say("panel.open"), "href": "/planner/"}],
        }
    ]
    after = blocks_of("upnext", found.get("upnext") or {}, label=say("panel.coming"))
    if after:
        tabs.append(
            {
                "id": "next",
                "label": say("panel.upcoming"),
                "blocks": after,
                "actions": [{"label": say("panel.week"), "href": "/planner/"}],
            }
        )
    calendar = month_block(found.get("calendar"), now)
    if calendar:
        tabs.append(
            {
                "id": "month",
                "label": say("panel.month"),
                "blocks": [calendar],
                "actions": [{"label": say("panel.open_month"), "href": "/planner/"}],
            }
        )
    questions = [
        {
            "text": say("panel.ask.today"),
            "words": words("panel.ask.today.words"),
            "tab": "today",
        }
    ]
    if after:
        questions.append(
            {
                "text": say("panel.ask.next"),
                "words": words("panel.ask.next.words"),
                "tab": "next",
            }
        )
    if calendar:
        questions.append(
            {
                "text": say("panel.ask.month"),
                "words": words("panel.ask.month.words"),
                "tab": "month",
            }
        )
    return panel("day", order=10, headlines=headlines, tabs=tabs, questions=questions)
