from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_module.service import Service
from arga_tenancy import current_spaces, require_person
from outings import (
    agenda,
    area,
    by_hand,
    explore,
    foryou,
    hub,
    maps,
    planned,
    profile,
    publisher,
    spaces,
    tools,
    widgets,
    wishes,
)
from outings import panel as home_panel
from outings.common import Conflict, NotFound

MODULE_ID = "outings"


def _coded(run):

    async def coded(connection: AsyncConnection, arguments: Any, **extra: Any) -> dict[str, Any]:
        try:
            return await run(connection, arguments, **extra)
        except NotFound as error:
            raise HTTPException(
                status_code=404, detail={"code": "NOT_FOUND", "message": f"not found: {error}"}
            ) from error
        except Conflict as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error

    return coded


service = Service(
    MODULE_ID,
    "Outings",
    tools={
        name: dataclasses.replace(tool, run=_coded(tool.run)) for name, tool in tools.TOOLS.items()
    },
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={NotFound: 404, Conflict: 409},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_app = service.as_app
_edit = service.edit


@app.get("/planned")
async def list_planned() -> list[planned.Planned]:
    return await _edit(planned.planned)


@app.post("/wishes/{wish_id}/idea")
async def wish_to_idea(wish_id: UUID) -> planned.Idea:
    return await _hub(_edit, planned.to_idea, str(wish_id))


@app.get("/wishes")
async def list_wishes(
    kind: wishes.Kind | None = None,
    archived: bool = False,
    q: str | None = Query(default=None, max_length=100),
) -> list[wishes.Wish]:
    return await _edit(wishes.wishes, kind, archived, q)


@app.post("/wishes", status_code=201)
async def add_wish(request: wishes.WishIn) -> wishes.Wish:
    return await _edit(wishes.add, request)


@app.get("/wishes/{wish_id}")
async def read_wish(wish_id: UUID) -> wishes.Wish:
    return await _edit(wishes.wish, str(wish_id))


@app.patch("/wishes/{wish_id}")
async def update_wish(wish_id: UUID, patch: wishes.WishPatch) -> wishes.Wish:
    return await _edit(wishes.update, str(wish_id), patch)


@app.post("/wishes/{wish_id}/done")
async def mark_done(wish_id: UUID) -> wishes.Wish:
    return await _edit(wishes.mark_done, str(wish_id))


@app.post("/wishes/{wish_id}/restore")
async def restore_wish(wish_id: UUID) -> wishes.Wish:
    return await _edit(wishes.restore, str(wish_id))


class SpaceIn(BaseModel):
    space_id: UUID | None


@app.put("/wishes/{wish_id}/space")
async def share_wish(wish_id: UUID, request: SpaceIn) -> wishes.Wish:
    require_person()
    try:
        found = await spaces.of_caller()
    except spaces.Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    current_spaces.set(tuple(UUID(space["id"]) for space in found))
    if request.space_id is not None and str(request.space_id) not in {s["id"] for s in found}:
        raise HTTPException(status_code=404, detail="you are not in that space")
    space = str(request.space_id) if request.space_id else None
    return await _edit(wishes.share, str(wish_id), space)


@app.delete("/wishes/{wish_id}", status_code=204)
async def delete_wish(wish_id: UUID) -> Response:
    await _edit(wishes.remove, str(wish_id))
    return Response(status_code=204)


@app.put("/wishes/{wish_id}/photo")
async def upload_photo(wish_id: UUID, request: Request) -> wishes.Wish:
    declared = int(request.headers.get("content-length") or 0)
    if declared > wishes.PHOTO_LIMIT:
        raise HTTPException(status_code=413, detail="la foto pasa de 8 MB")
    try:
        shrunk = await wishes.shrink(await request.body())
    except Conflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return await _edit(wishes.set_photo, str(wish_id), shrunk)


@app.delete("/wishes/{wish_id}/photo")
async def delete_photo(wish_id: UUID) -> wishes.Wish:
    return await _edit(wishes.remove_photo, str(wish_id))


@app.get("/wishes/{wish_id}/photo")
async def read_photo(
    wish_id: UUID, size: str = Query(default="full", pattern="^(full|thumb)$")
) -> Response:
    content, kind = await _edit(wishes.photo, str(wish_id), size == "thumb")
    return Response(content, media_type=kind, headers={"cache-control": "private, max-age=604800"})


@app.get("/agenda")
async def read_agenda(
    period: agenda.Period = "weekend",
    category: agenda.Category | None = None,
    town: str | None = Query(default=None, max_length=80),
) -> dict:
    first, last = agenda.window(period)

    async def run(connection):
        return await agenda.events(connection, first, last, category, town)

    found = await _edit(run)
    return {"period": period, "from": first, "to": last, "events": found}


@app.get("/explore")
async def explore_agenda(
    q: str | None = Query(default=None, max_length=100),
    when: explore.When = "quarter",
    zone: explore.Zone | None = None,
    category: agenda.Category | None = None,
    sort: explore.Sort = "date",
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    since: date | None = None,
) -> explore.Found:
    return await _edit(
        explore.search, q, when, None, None, zone, category, sort, limit, offset, None, since
    )


@app.get("/foryou")
async def read_for_you() -> list[foryou.Pick]:
    return await _edit(foryou.picks)


@app.get("/mine")
async def read_mine(
    first: Annotated[date, Query(alias="from")], last: Annotated[date, Query(alias="to")]
) -> dict:
    if (last - first).days > 120 or last < first:
        raise HTTPException(status_code=422, detail="from one to one hundred and twenty days")
    found = await _edit(explore.mine, first, last)
    return {"from": first, "to": last, "events": found}


@app.put("/events/{event_id}/dismiss")
async def dismiss_event(event_id: UUID, on: bool = True) -> agenda.Event:
    return await _edit(explore.dismiss, str(event_id), on)


@app.get("/interests")
async def read_interests() -> list[explore.Interest]:
    return await _edit(explore.interests)


@app.post("/interests", status_code=201)
async def add_interest(request: explore.InterestIn) -> explore.Interest:
    return await _edit(explore.add_interest, request)


@app.delete("/interests/{interest_id}")
async def remove_interest(interest_id: UUID) -> explore.Interest:
    return await _edit(explore.remove_interest, str(interest_id))


@app.get("/events/{event_id}")
async def read_event(event_id: UUID) -> agenda.Event:
    return await _edit(agenda.event, str(event_id))


@app.get("/events/{event_id}/near")
async def wishes_near_event(event_id: UUID) -> list[area.Near]:

    async def run(connection):
        found = await agenda.event(connection, str(event_id))
        if found.lat is None or found.lon is None:
            return []
        return await area.near(connection, found.lat, found.lon)

    return await _edit(run)


class AreaOut(BaseModel):
    id: str
    name: str
    near: str
    region: str
    near_box: profile.Box
    region_box: profile.Box
    map: bool
    relief: str | None


@app.get("/area")
async def read_area() -> AreaOut:
    found = profile.current()
    return AreaOut(
        id=found.id,
        name=found.name,
        near=found.near.name,
        region=found.region.name,
        near_box=found.near.box,
        region_box=found.region.box,
        map=maps.has_map(service.ui_dist(), found.id),
        relief=found.map.relief.attribution if found.map.relief else None,
    )


@app.get("/map")
async def read_map(days: int = Query(default=30, ge=1, le=366)) -> area.MapOut:
    return await _edit(area.points, days)


@app.post("/events/{event_id}/save")
async def save_event(event_id: UUID) -> wishes.Wish:

    async def run(connection):
        return await wishes.wish(connection, await agenda.save(connection, str(event_id)))

    return await _edit(run)


@app.post("/events/{event_id}/split/{source_id}")
async def split_event(event_id: UUID, source_id: UUID) -> agenda.Event:
    return await _edit(agenda.split, str(event_id), str(source_id))


@app.put("/events/{event_id}/calendar")
async def to_calendar(event_id: UUID, on: bool = True) -> agenda.Event:
    return await _edit(agenda.to_calendar, str(event_id), on)


async def _hub(call, *args):
    try:
        return await call(*args)
    except hub.Refused as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.get("/agenda/sources")
async def agenda_sources() -> dict:
    plugged = await _edit(agenda.sources)
    try:
        offered = await hub.catalogue()
        failed = None
    except hub.Refused as error:
        offered, failed = {"sources": []}, str(error)
    return {"plugged": plugged, "offered": offered.get("sources", []), "failed": failed}


class PlugIn(BaseModel):
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    params: dict = Field(default_factory=dict)


@app.post("/agenda/sources", status_code=201)
async def plug_source(request: PlugIn) -> dict:
    return await _hub(hub.plug, request.provider, request.label, request.params)


@app.get("/agenda/prompt")
async def agenda_prompt(days: int = Query(default=90, ge=7, le=180)) -> dict:
    return {"prompt": await _edit(by_hand.brief, days)}


@app.delete("/agenda/sources/{connection_id}")
async def unplug_source(connection_id: UUID) -> dict:
    return {"removed": await _hub(hub.unplug, str(connection_id))}


@app.get("/places/search")
async def search_places(q: str = Query(min_length=2, max_length=120)) -> dict:
    found = await hub.search(q)
    return {
        "candidates": [
            {**wishes.place_of(one).model_dump(), "kind": one.get("kind")}
            for one in found.get("candidates", [])
        ],
        "failed": found.get("failed", []),
    }


@app.get(f"/{MODULE_ID}/map/v-{{version}}/{{path:path}}")
async def map_file(version: str, path: str) -> Response:
    return maps.serve(service.ui_dist(), version, path)


service.serve_ui()
