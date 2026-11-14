from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from arga_module import preferences
from arga_module.service import Service
from planner import apps, calendar, feeds, hub, publisher, tools, widgets
from planner import panel as home_panel

MODULE_ID = "planner"


def _told(run):

    async def told(*args: Any, **extra: Any) -> dict[str, Any]:
        try:
            return await run(*args, **extra)
        except (calendar.Invalid, calendar.NotFound, hub.Refused) as error:
            return {"error": str(error)}

    return told


service = Service(
    MODULE_ID,
    "Planner",
    tools={
        name: dataclasses.replace(tool, run=_told(tool.run)) for name, tool in tools.TOOLS.items()
    },
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={calendar.NotFound: 404, calendar.Invalid: 422},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_app = service.as_app


async def _edit(action, *args):
    return await service.edit(action, *args)


@app.get("/calendars")
async def read_calendars() -> list[calendar.Calendar]:
    async with as_app() as connection:
        await feeds.derive(connection)
        await apps.derive(connection)
    layers = await _edit(calendar.calendars)
    if any(layer.origin == "app" for layer in layers):
        movable = await apps.movable()
        for layer in layers:
            layer.movable = layer.origin == "app" and apps.module_of(layer.app or "") in movable
    return layers


@app.post("/calendars", status_code=201)
async def create_calendar(request: calendar.CalendarIn) -> calendar.Calendar:
    return await _edit(calendar.create_calendar, request)


@app.patch("/calendars/{calendar_id}")
async def update_calendar(calendar_id: str, request: calendar.CalendarPatch) -> calendar.Calendar:
    return await _edit(calendar.update_calendar, calendar_id, request)


class OrderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


@app.put("/calendars/order")
async def reorder_calendars(request: OrderIn) -> list[calendar.Calendar]:
    return await _edit(calendar.reorder_calendars, request.ids)


class SubscribeIn(BaseModel):
    provider: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    name: str = Field(min_length=1, max_length=60)
    tone: int = Field(ge=1, le=10)
    params: dict[str, Any] = Field(default_factory=dict)


LAYER_OF_CONNECTION = text(
    "select id from planner.planner_calendar where connection_id = cast(:connection as uuid) limit 1"
)


@app.post("/subscriptions", status_code=201)
async def subscribe(request: SubscribeIn, response: Response) -> calendar.Calendar:
    name = request.name.strip()
    try:
        plugged = await hub.plug(
            request.provider, name, request.params, {"name": name, "tone": request.tone}
        )
    except hub.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    settings = plugged.get("settings") or {}
    async with as_app() as connection:
        if plugged.get("existing"):
            existing = await connection.scalar(
                LAYER_OF_CONNECTION, {"connection": plugged["connection"]}
            )
            if existing:
                response.status_code = 200
                return await calendar.calendar(connection, str(existing))
        layer = await feeds.add_layer(
            connection,
            plugged["connection"],
            str(settings.get("name") or name),
            int(settings.get("tone") or request.tone),
        )
        return await calendar.calendar(connection, layer)


def _ask_where_the_person_lives(asks: list[dict[str, Any]]) -> None:
    person = preferences.current()
    if not person.country:
        return
    lives = {"country": person.country}
    if person.region and person.region.startswith(f"{person.country}-"):
        lives["region"] = person.region
    for ask in asks:
        if ask.get("kind") == "pick" and ask.get("key") in lives:
            ask["default"] = lives[ask["key"]]


@app.get("/subscriptions/catalogue")
async def subscription_catalogue() -> dict:
    try:
        found = await hub.catalogue()
    except hub.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error
    sources = found.get("sources") or []
    async with as_app() as connection:
        layers = [
            one
            for one in await calendar.calendars(connection)
            if one.origin == "subscription" and one.connection_id
        ]
    known = {one["provider"] for one in sources}
    for source in sources:
        _ask_where_the_person_lives(source.get("asks") or [])
        source["subscribed"] = [
            one.model_dump(mode="json")
            for one in layers
            if one.subscription and one.subscription.provider == source["provider"]
        ]
    others = [
        one.model_dump(mode="json")
        for one in layers
        if not one.subscription or one.subscription.provider not in known
    ]
    return {"groups": found.get("groups") or [], "sources": sources, "others": others}


@app.get("/subscriptions/search")
async def subscription_search(
    provider: str = Query(pattern=r"^[a-z][a-z0-9_]{1,40}$"),
    ask: str = Query(pattern=r"^[a-z][a-z0-9_]{0,40}$"),
    q: str | None = Query(default=None, max_length=60),
    parent: str | None = Query(default=None, max_length=60),
) -> dict:
    try:
        return await hub.search(provider, ask, q, parent)
    except hub.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.delete("/subscriptions/{calendar_id}", status_code=204)
async def unsubscribe(calendar_id: UUID) -> None:
    async with as_app() as connection:
        try:
            layer = await calendar.calendar(connection, str(calendar_id))
        except calendar.NotFound as error:
            raise HTTPException(status_code=404, detail=f"no existe: {calendar_id}") from error
    if layer.origin != "subscription" or not layer.connection_id:
        raise HTTPException(status_code=409, detail="that layer is not a subscription")
    try:
        await hub.unsubscribe(layer.connection_id)
    except hub.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.post("/feed/{feed_id}/hide", status_code=204)
async def hide(feed_id: str) -> None:
    try:
        UUID(feed_id)
        async with as_app() as connection:
            await feeds.hide(connection, feed_id)
    except (ValueError, feeds.NotFound) as error:
        raise HTTPException(status_code=404, detail=f"no existe: {feed_id}") from error


@app.get("/occurrences")
async def read_occurrences(
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
    calendars: Annotated[list[str] | None, Query()] = None,
) -> list[calendar.Occurrence]:
    return await _edit(calendar.occurrences, start, end, calendars)


@app.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[calendar.Occurrence]:
    return await _edit(calendar.search, q, None, None, limit)


@app.get("/events/{event_id}")
async def read_event(event_id: str) -> calendar.Event:
    return await _edit(calendar.event, event_id)


@app.post("/events", status_code=201)
async def create_event(request: calendar.EventIn) -> calendar.Event:
    return await _edit(calendar.create, request)


class UpdateIn(BaseModel):
    changes: calendar.EventPatch
    scope: Literal["this", "following", "all"] = "all"
    original_start: str | None = None


@app.patch("/events/{event_id}")
async def update_event(event_id: str, request: UpdateIn) -> calendar.Event:
    return await _edit(
        calendar.update, event_id, request.changes, request.scope, request.original_start
    )


class CancelIn(BaseModel):
    scope: Literal["this", "following", "all"] = "all"
    original_start: str | None = None


@app.post("/events/{event_id}/cancel")
async def cancel_event(event_id: str, request: CancelIn) -> calendar.Event:
    return await _edit(calendar.cancel, event_id, request.scope, request.original_start)


class MoveIn(BaseModel):
    start: str = Field(min_length=10, max_length=40)
    end: str = Field(min_length=10, max_length=40)
    all_day: bool = False


@app.post("/app-events/{app_event_id}/move")
async def move_app_event(app_event_id: str, request: MoveIn) -> calendar.Occurrence:
    try:
        await apps.move(as_app, app_event_id, request.start, request.end, request.all_day)
        async with as_app() as connection:
            return calendar.from_app(await apps.by_id(connection, app_event_id))
    except apps.NotFound as error:
        raise HTTPException(status_code=404, detail=f"no existe: {app_event_id}") from error
    except apps.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


service.serve_ui()
