from __future__ import annotations

import hmac
import os
import re
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
from arga_module.service import Service
from arga_tenancy import current_spaces, require_person
from travel import (
    bookings,
    covers,
    documents,
    geo,
    hub,
    ideas,
    itinerary,
    journal,
    lists,
    money,
    notes,
    plans,
    publisher,
    spaces,
    streets,
    today,
    tools,
    travel,
    widgets,
)
from travel import panel as home_panel
from travel.db import SCHEMA, engine

MODULE_ID = "travel"
UI_ROOT = f"/{MODULE_ID}"
GEO_FILES = ("countries.json", "regions.json")

service = Service(
    MODULE_ID,
    "Travel",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    errors={travel.NotFound: 404, travel.Conflict: 409},
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_app = service.as_app
ui_dist = service.ui_dist


async def readyz() -> dict:
    try:
        async with engine().connect() as connection:
            found = await connection.scalar(
                text("select 1 from information_schema.schemata where schema_name = :schema"),
                {"schema": SCHEMA},
            )
    except Exception as error:  # noqa: BLE001 -- cualquier fallo de conexión es "no listo"
        raise HTTPException(status_code=503, detail=f"sin base de datos: {error}") from error

    if not found:
        raise HTTPException(
            status_code=503,
            detail=f"el schema '{SCHEMA}' no existe todavía; lo aprovisiona el kernel al "
            f"registrar el manifiesto",
        )
    if not (ui_dist() / "index.html").is_file():
        raise HTTPException(status_code=503, detail=f"la app no está construida en {ui_dist()}")
    if not all((geo.geo_dir() / name).is_file() for name in GEO_FILES):
        raise HTTPException(status_code=503, detail=f"faltan las geometrías en {geo.geo_dir()}")
    return {"status": "ready", "module": MODULE_ID, "schema": SCHEMA}


app.add_api_route("/readyz", readyz, methods=["GET"])
app.router.routes.insert(0, app.router.routes.pop())


async def _edit(action, *args):
    return await service.edit(action, *args)


IdeaList = list[ideas.Idea]


class Atlas(BaseModel):
    trips: list[travel.Trip]
    others: list[travel.OtherPlace]
    home: travel.Place | None = None
    ideas: IdeaList = []


async def _atlas(connection: AsyncConnection) -> Atlas:
    return Atlas(
        trips=await travel.all_trips(connection),
        others=await travel.other_places(connection),
        home=await travel.home(connection),
        ideas=[one for one in await ideas.ideas(connection) if not one.archived],
    )


@app.get("/atlas")
async def atlas() -> Atlas:
    return await _edit(_atlas)


@app.get("/stats")
async def read_stats() -> travel.Stats:
    found = await _edit(_atlas)
    return travel.stats(travel.lived(found.trips), found.others)


@app.post("/others", status_code=201)
async def add_other_place(request: travel.OtherPlaceIn) -> travel.OtherPlace:
    return await _edit(travel.add_other_place, request)


@app.delete("/others/{other_id}", status_code=204)
async def delete_other_place(other_id: UUID) -> Response:
    await _edit(travel.delete_other_place, str(other_id))
    return Response(status_code=204)


@app.put("/home")
async def set_home(request: travel.HomeIn) -> travel.Place:
    return await _edit(travel.set_home, request)


@app.delete("/home", status_code=204)
async def clear_home() -> Response:
    await _edit(travel.clear_home)
    return Response(status_code=204)


@app.get("/concepts")
async def concepts() -> dict[str, list[str]]:
    return {category: list(names) for category, names in travel.CATEGORIES.items()}


@app.get("/trips/{trip_id}")
async def read_trip(trip_id: UUID) -> travel.Trip:
    return await _edit(travel.trip, str(trip_id))


@app.post("/trips", status_code=201)
async def create_trip(request: travel.TripIn) -> travel.Trip:
    return await _edit(travel.create_trip, request)


@app.put("/trips/{trip_id}")
async def update_trip(trip_id: UUID, request: travel.TripIn, shift: bool = False) -> travel.Trip:
    return await _edit(travel.update_trip, str(trip_id), request, False, shift)


class StatusIn(BaseModel):
    status: travel.Status


@app.put("/trips/{trip_id}/status")
async def set_status(trip_id: UUID, request: StatusIn) -> travel.Trip:
    return await _edit(travel.set_status, str(trip_id), request.status)


@app.delete("/trips/{trip_id}", status_code=204)
async def delete_trip(trip_id: UUID) -> Response:
    await _edit(travel.delete_trip, str(trip_id))
    return Response(status_code=204)


class ArchiveIn(BaseModel):
    archived: bool


@app.put("/trips/{trip_id}/archived")
async def archive_trip(trip_id: UUID, request: ArchiveIn) -> travel.Trip:
    return await _edit(travel.archive_trip, str(trip_id), request.archived)


async def fresh_spaces() -> list[dict]:
    require_person()
    try:
        found = await spaces.of_caller()
    except spaces.Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    current_spaces.set(tuple(UUID(space["id"]) for space in found))
    return found


class SpaceIn(BaseModel):
    space_id: UUID | None


@app.put("/trips/{trip_id}/space")
async def share_trip(trip_id: UUID, request: SpaceIn) -> travel.Trip:
    found = await fresh_spaces()
    if request.space_id is not None and str(request.space_id) not in {s["id"] for s in found}:
        raise HTTPException(status_code=404, detail="no estás en ese espacio")
    space = str(request.space_id) if request.space_id else None
    return await _edit(travel.share_trip, str(trip_id), space)


@app.post("/trips/{trip_id}/stays", status_code=201)
async def add_stay(trip_id: UUID, request: travel.StayIn) -> travel.Trip:
    return await _edit(travel.add_stay, str(trip_id), request)


@app.put("/trips/{trip_id}/stays/{stay_id}")
async def update_stay(trip_id: UUID, stay_id: UUID, request: travel.StayIn) -> travel.Trip:
    return await _edit(travel.update_stay, str(trip_id), str(stay_id), request)


@app.post("/trips/{trip_id}/visits", status_code=201)
async def add_visit(trip_id: UUID, request: travel.VisitIn) -> travel.Trip:
    return await _edit(travel.add_visit, str(trip_id), request)


@app.post("/trips/{trip_id}/legs", status_code=201)
async def add_leg(trip_id: UUID, request: travel.LegIn) -> travel.Trip:
    return await _edit(travel.add_leg, str(trip_id), request)


@app.put("/trips/{trip_id}/legs/{leg_id}")
async def update_leg(trip_id: UUID, leg_id: UUID, request: travel.LegIn) -> travel.Trip:
    return await _edit(travel.update_leg, str(trip_id), str(leg_id), request)


@app.post("/trips/{trip_id}/expenses", status_code=201)
async def add_expense(trip_id: UUID, request: travel.ExpenseIn) -> travel.Trip:
    return await _edit(travel.add_expense, str(trip_id), request)


@app.put("/trips/{trip_id}/expenses/{expense_id}")
async def update_expense(trip_id: UUID, expense_id: UUID, request: travel.ExpenseIn) -> travel.Trip:
    return await _edit(travel.update_expense, str(trip_id), str(expense_id), request)


@app.get("/trips/{trip_id}/travellers")
async def read_travellers(trip_id: UUID) -> list[money.Traveller]:
    return await _edit(money.ensure_travellers, str(trip_id))


@app.get("/trips/{trip_id}/bookings")
async def read_bookings(trip_id: UUID) -> list[bookings.Booking]:
    return await _edit(bookings.bookings, str(trip_id))


@app.get("/tiles/{z}/{x}/{y}")
async def read_tile(z: int, x: int, y: int) -> Response:
    if not 0 <= z <= 15 or not (0 <= x < 1 << z and 0 <= y < 1 << z):
        raise HTTPException(status_code=404, detail="esa tesela no existe")
    try:
        data = await _edit(streets.tile, z, x, y)
    except streets.Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    cache = {"cache-control": "private, max-age=2592000, immutable"}
    if data is None:
        return Response(status_code=204, headers=cache)
    return Response(content=data, media_type="application/x-protobuf", headers=cache)


@app.get("/ideas")
async def read_ideas() -> list[ideas.Idea]:
    return await _edit(ideas.ideas)


@app.post("/ideas", status_code=201)
async def create_idea(request: ideas.IdeaIn) -> ideas.Idea:
    return await _edit(ideas.create_idea, request)


@app.get("/ideas/{idea_id}")
async def read_idea(idea_id: UUID) -> ideas.Idea:
    return await _edit(ideas.idea, str(idea_id))


@app.put("/ideas/{idea_id}")
async def update_idea(idea_id: UUID, request: ideas.IdeaIn) -> ideas.Idea:
    return await _edit(ideas.update_idea, str(idea_id), request)


@app.delete("/ideas/{idea_id}", status_code=204)
async def delete_idea(idea_id: UUID) -> Response:
    await _edit(ideas.delete_idea, str(idea_id))
    return Response(status_code=204)


@app.put("/ideas/{idea_id}/archived")
async def archive_idea(idea_id: UUID, request: ArchiveIn) -> ideas.Idea:
    return await _edit(ideas.archive_idea, str(idea_id), request.archived)


class IdeaPlaceIn(BaseModel):
    place_id: str
    note: str | None = Field(default=None, max_length=500)


@app.post("/ideas/{idea_id}/places", status_code=201)
async def add_idea_place(idea_id: UUID, request: IdeaPlaceIn) -> ideas.Idea:
    return await _edit(ideas.add_place, str(idea_id), request.place_id, request.note)


@app.delete("/ideas/{idea_id}/places/{idea_place_id}")
async def remove_idea_place(idea_id: UUID, idea_place_id: UUID) -> ideas.Idea:
    return await _edit(ideas.remove_place, str(idea_id), str(idea_place_id))


class PlanIn(BaseModel):
    starts_on: date
    ends_on: date
    title: str | None = Field(default=None, min_length=1, max_length=120)
    travellers: int = Field(default=1, ge=1, le=50)


@app.post("/ideas/{idea_id}/plan", status_code=201)
async def plan_idea(idea_id: UUID, request: PlanIn) -> travel.Trip:
    if request.ends_on < request.starts_on:
        raise HTTPException(status_code=422, detail="el viaje no puede acabar antes de empezar")
    return await _edit(
        ideas.plan_idea,
        str(idea_id),
        request.starts_on,
        request.ends_on,
        request.title,
        request.travellers,
    )


@app.put("/ideas/{idea_id}/space")
async def share_idea(idea_id: UUID, request: SpaceIn) -> ideas.Idea:
    found = await fresh_spaces()
    if request.space_id is not None and str(request.space_id) not in {s["id"] for s in found}:
        raise HTTPException(status_code=404, detail="no estás en ese espacio")
    space = str(request.space_id) if request.space_id else None
    return await _edit(ideas.share_idea, str(idea_id), space)


@app.get("/today")
async def read_today(day: date | None = None) -> today.Today:
    return await _edit(today.today, day)


@app.get("/weather/{kind}")
async def read_weather(
    kind: Literal["forecast", "climate"],
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
) -> dict:
    found = await (hub.forecast(lat, lon) if kind == "forecast" else hub.climate(lat, lon))
    return {"weather": found.get("weather"), "failed": found.get("failed")}


@app.get("/nearby")
async def read_nearby(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    kind: Literal["food", "sights", "nature", "shopping", "nightlife"] = "sights",
    radius: int = Query(default=1000, ge=100, le=3000),
) -> dict:
    return await hub.nearby(lat, lon, kind, radius, 20)


@app.get("/trips/{trip_id}/days/{day}/route")
async def read_day_route(
    trip_id: UUID, day: date, profile: streets.Profile = "foot"
) -> streets.DayRoute:
    return await _edit(streets.day_route, str(trip_id), day, profile)


@app.get("/trips/{trip_id}/days")
async def read_days(trip_id: UUID) -> itinerary.Itinerary:
    return await _edit(itinerary.itinerary, str(trip_id))


@app.post("/trips/{trip_id}/blocks", status_code=201)
async def add_block(trip_id: UUID, request: itinerary.BlockIn) -> itinerary.Itinerary:
    return await _edit(itinerary.add_block, str(trip_id), request)


@app.put("/trips/{trip_id}/blocks/{block_id}")
async def update_block(
    trip_id: UUID, block_id: UUID, request: itinerary.BlockIn
) -> itinerary.Itinerary:
    return await _edit(itinerary.update_block, str(trip_id), str(block_id), request)


class PositionIn(BaseModel):
    day: date | None
    position: int = Field(ge=0)


@app.put("/trips/{trip_id}/blocks/{block_id}/position")
async def move_block(trip_id: UUID, block_id: UUID, request: PositionIn) -> itinerary.Itinerary:
    return await _edit(
        itinerary.move_block, str(trip_id), str(block_id), request.day, request.position
    )


class DayTitleIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)


@app.put("/trips/{trip_id}/days/{day}/title")
async def set_day_title(trip_id: UUID, day: date, request: DayTitleIn) -> itinerary.Itinerary:
    return await _edit(itinerary.set_day_title, str(trip_id), day, request.title)


@app.delete("/trips/{trip_id}/blocks/{block_id}")
async def remove_block(trip_id: UUID, block_id: UUID) -> itinerary.Itinerary:
    return await _edit(itinerary.remove_block, str(trip_id), str(block_id))


@app.patch("/trips/{trip_id}/travellers/{traveller_id}")
async def update_traveller(
    trip_id: UUID, traveller_id: UUID, request: money.TravellerChange
) -> list[money.Traveller]:
    members: dict[str, set[str]] = {}
    if "member_user_id" in request.model_fields_set and request.member_user_id is not None:
        members = {
            space["id"]: {one["user_id"] for one in space.get("members", [])}
            for space in await fresh_spaces()
        }
    return await _edit(money.update_traveller, str(trip_id), str(traveller_id), request, members)


@app.get("/trips/{trip_id}/balance")
async def read_balance(trip_id: UUID) -> money.Balance:
    return await _edit(money.balance, str(trip_id))


@app.post("/trips/{trip_id}/settlements", status_code=201)
async def add_settlement(trip_id: UUID, request: money.SettlementIn) -> money.Balance:
    return await _edit(money.settle, str(trip_id), request)


@app.delete("/trips/{trip_id}/settlements/{settlement_id}")
async def remove_settlement(trip_id: UUID, settlement_id: UUID) -> money.Balance:
    return await _edit(money.unsettle, str(trip_id), str(settlement_id))


@app.get("/trips/{trip_id}/journal")
async def read_journal(trip_id: UUID) -> list[journal.Entry]:
    return await _edit(journal.entries, str(trip_id))


@app.put("/trips/{trip_id}/journal/{day}")
async def write_journal(
    trip_id: UUID, day: date, request: journal.JournalIn
) -> list[journal.Entry]:
    return await _edit(journal.write, str(trip_id), day, request)


@app.get("/trips/{trip_id}/notes")
async def read_notes(trip_id: UUID) -> list[notes.Note]:
    return await _edit(notes.notes, str(trip_id))


@app.post("/trips/{trip_id}/notes", status_code=201)
async def add_note(trip_id: UUID, request: notes.NoteIn) -> list[notes.Note]:
    return await _edit(notes.add_note, str(trip_id), request)


@app.put("/trips/{trip_id}/notes/{note_id}")
async def update_note(trip_id: UUID, note_id: UUID, request: notes.NoteIn) -> list[notes.Note]:
    return await _edit(notes.update_note, str(trip_id), str(note_id), request)


@app.delete("/trips/{trip_id}/notes/{note_id}")
async def remove_note(trip_id: UUID, note_id: UUID) -> list[notes.Note]:
    return await _edit(notes.remove_note, str(trip_id), str(note_id))


@app.get("/trips/{trip_id}/checklist")
async def read_checklist(trip_id: UUID) -> list[lists.Item]:
    return await _edit(lists.items, str(trip_id))


@app.post("/trips/{trip_id}/checklist", status_code=201)
async def add_check_items(trip_id: UUID, request: list[lists.ItemIn]) -> list[lists.Item]:
    return await _edit(lists.add_items, str(trip_id), request)


class CopyIn(BaseModel):
    from_trip_id: UUID
    list: lists.ListKind | None = None


@app.post("/trips/{trip_id}/checklist/copy")
async def copy_checklist(trip_id: UUID, request: CopyIn) -> list[lists.Item]:
    return await _edit(lists.copy_from, str(trip_id), str(request.from_trip_id), request.list)


@app.patch("/trips/{trip_id}/checklist/{item_id}")
async def change_check_item(
    trip_id: UUID, item_id: UUID, request: lists.ItemChange
) -> list[lists.Item]:
    return await _edit(lists.change_item, str(trip_id), str(item_id), request)


@app.delete("/trips/{trip_id}/checklist/{item_id}")
async def remove_check_item(trip_id: UUID, item_id: UUID) -> list[lists.Item]:
    return await _edit(lists.remove_item, str(trip_id), str(item_id))


@app.get("/trips/{trip_id}/documents")
async def read_documents(trip_id: UUID) -> list[documents.Document]:
    return await _edit(documents.documents, str(trip_id))


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Travel no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Travel")
    if capability != contracts.TRIPS_IDEA:
        raise HTTPException(status_code=404, detail=f"Travel no sabe hacer '{capability}'")
    require_person()
    try:
        asked = contracts.TripIdea.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    made = await _edit(plans.make_idea, asked)
    print(f"idea       pedida por {x_arga_module}", flush=True)
    return made


@app.put("/trips/{trip_id}/cover")
async def upload_cover(trip_id: UUID, request: Request) -> travel.Trip:
    if int(request.headers.get("content-length") or 0) > covers.LIMIT:
        raise HTTPException(status_code=413, detail="la foto pasa de 12 MB")
    try:
        cover = await covers.prepare(await request.body())
    except travel.Conflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return await _edit(covers.set_cover, str(trip_id), cover)


@app.delete("/trips/{trip_id}/cover")
async def remove_cover(trip_id: UUID) -> travel.Trip:
    return await _edit(covers.remove_cover, str(trip_id))


@app.get("/trips/{trip_id}/cover")
async def read_cover(trip_id: UUID, size: Literal["full", "thumb"] = "full") -> Response:
    body = await _edit(covers.content, str(trip_id), size)
    return Response(
        body,
        media_type="image/jpeg",
        headers={"cache-control": "private, max-age=31536000, immutable"},
    )


@app.post("/trips/{trip_id}/documents", status_code=201)
async def upload_document(
    trip_id: UUID,
    request: Request,
    name: str = "",
    link_type: documents.LinkKind | None = None,
    link_id: UUID | None = None,
) -> list[documents.Document]:
    declared = int(request.headers.get("content-length") or 0)
    if declared > documents.LIMIT:
        raise HTTPException(status_code=413, detail="el fichero pasa de 20 MB")
    body = await request.body()
    kind = request.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
    return await _edit(
        documents.attach,
        str(trip_id),
        name,
        kind,
        body,
        link_type,
        str(link_id) if link_id else None,
    )


@app.get("/trips/{trip_id}/documents/{document_id}/file")
async def read_document(trip_id: UUID, document_id: UUID) -> Response:
    name, kind, body = await _edit(documents.content, str(trip_id), str(document_id))
    return Response(
        body,
        media_type=kind,
        headers={
            "content-disposition": f'inline; filename="{documents.clean_name(name)}"',
            "cache-control": "private, max-age=31536000, immutable",
        },
    )


@app.patch("/trips/{trip_id}/documents/{document_id}")
async def change_document(
    trip_id: UUID, document_id: UUID, request: documents.DocumentChange
) -> list[documents.Document]:
    return await _edit(documents.change, str(trip_id), str(document_id), request)


@app.delete("/trips/{trip_id}/documents/{document_id}")
async def remove_document(trip_id: UUID, document_id: UUID) -> list[documents.Document]:
    return await _edit(documents.remove, str(trip_id), str(document_id))


@app.delete("/trips/{trip_id}/{part}/{part_id}")
async def delete_part(trip_id: UUID, part: str, part_id: UUID) -> travel.Trip:
    if part not in travel.PARTS:
        raise HTTPException(status_code=404, detail=f"un viaje no tiene '{part}'")
    return await _edit(travel.delete_part, str(trip_id), part, str(part_id))


@app.get("/places")
async def list_places(
    query: str | None = Query(default=None, max_length=120),
) -> list[travel.Place]:
    return await _edit(travel.places, query)


@app.get("/places/search")
async def search_places(query: str = Query(min_length=2, max_length=120)) -> dict:
    return await hub.search(query)


@app.post("/places", status_code=201)
async def save_place(request: travel.PlaceIn) -> travel.Place:
    return await _edit(travel.save_place, request)


class CategoryIn(BaseModel):
    category: travel.PlaceCategory | None


@app.put("/places/{place_id}/category")
async def set_place_category(place_id: UUID, request: CategoryIn) -> travel.Place:
    place, _ = await _edit(
        travel.update_place, str(place_id), None, None, request.category or "other"
    )
    return place


@app.get(UI_ROOT + "/geo/{name}")
async def geometry(name: str) -> FileResponse:
    if name not in GEO_FILES:
        raise HTTPException(status_code=404, detail=f"no hay geometría '{name}'")
    return FileResponse(
        geo.geo_dir() / name,
        media_type="application/json",
        headers={"cache-control": "public, max-age=86400"},
    )


TRIP_APP = re.compile(r"viaje/[0-9a-f-]{36}/?")
MANIFEST_LINK = re.compile(r'\s*<link rel="manifest"[^>]*>')


def trip_app_page(html: str) -> str:
    return MANIFEST_LINK.sub("", html)


@app.get(UI_ROOT + "/viaje/{trip_id}")
@app.get(UI_ROOT + "/viaje/{trip_id}/")
async def trip_app(trip_id: str) -> HTMLResponse:
    if not TRIP_APP.fullmatch(f"viaje/{trip_id}"):
        raise HTTPException(status_code=404, detail=f"no existe: {trip_id}")
    index = ui_dist() / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="la app no está construida")
    return HTMLResponse(trip_app_page(index.read_text()), headers={"cache-control": "no-cache"})


service.serve_ui()
