from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import SPACES_GUC, format_spaces
from travel import (
    spaces,
    travel,
)
from travel.tools.common import DRY_RUN, SUMMARY_HELP, _edit, _given, _mutate, _summary


class CreateTrip(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    starts_on: date
    ends_on: date
    travellers: int = Field(
        default=1, ge=1, le=50, description="Cuántos erais. Los gastos se apuntan por persona."
    )
    companions: list[str] = Field(default=[], max_length=30, description="Con quién.")
    tags: list[str] = Field(
        default=[], max_length=20, description="Escapada, trabajo, verano, esquí…"
    )
    notes: str | None = Field(default=None, max_length=4000)
    status: travel.Status = Field(
        default="confirmed",
        description="plan si aún no está decidido o las fechas pueden moverse: se queda en Travel "
        "y no sale en el calendario. confirmed si es un viaje hecho o decidido.",
    )
    budget_eur_per_person: Decimal | None = Field(
        default=None, ge=0, decimal_places=2, description="Lo que se quiere gastar por persona."
    )
    summary: str | None = Field(default=None, max_length=1000, description=SUMMARY_HELP)


async def create_trip(connection: AsyncConnection, arguments: CreateTrip) -> dict[str, Any]:
    existing = await travel.find_duplicate(connection, arguments.title, arguments.starts_on)
    if existing:
        return {"created": False, "trip": _summary(await travel.trip(connection, existing))}
    try:
        created = await travel.create_trip(
            connection,
            travel.TripIn(
                **arguments.model_dump(exclude={"budget_eur_per_person"}),
                budget_eur=arguments.budget_eur_per_person,
            ),
            source="tool",
        )
    except ValueError as error:
        return {"created": False, "error": str(error), "code": "INVALID"}
    return {"created": True, "trip": _summary(created)}


class TripRef(BaseModel):
    trip_id: UUID


class UpdateTrip(TripRef):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    starts_on: date | None = None
    ends_on: date | None = None
    travellers: int | None = Field(default=None, ge=1, le=50)
    companions: list[str] | None = Field(
        default=None, max_length=30, description="La lista entera, que sustituye a la de antes."
    )
    tags: list[str] | None = Field(
        default=None, max_length=20, description="La lista entera, que sustituye a la de antes."
    )
    notes: str | None = Field(default=None, max_length=4000, description="`null` las borra.")
    summary: str | None = Field(
        default=None, max_length=1000, description=SUMMARY_HELP + " `null` lo quita."
    )
    keep_group_total: bool = Field(
        default=False,
        description="Al cambiar los viajeros, rehace los importes por persona para que el total "
        "del grupo sea el mismo. Sin esto, los importes por persona se quedan como estaban.",
    )
    budget_eur_per_person: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="El presupuesto por persona; null lo quita.",
    )
    shift_dates: bool = Field(
        default=False,
        description="Al cambiar starts_on, mueve con él los mismos días todo lo que tiene fecha: "
        "lugares principales, visitas y trayectos.",
    )
    dry_run: bool = DRY_RUN


async def update_trip(connection: AsyncConnection, arguments: UpdateTrip) -> dict[str, Any]:
    trip_id = str(arguments.trip_id)

    async def run() -> travel.Trip:
        current = await travel.trip(connection, trip_id)
        changes = _given(
            arguments,
            "title",
            "starts_on",
            "ends_on",
            "travellers",
            "companions",
            "tags",
            "notes",
            "summary",
        )
        for listed in ("companions", "tags"):
            if listed in changes and changes[listed] is None:
                changes[listed] = []
        if "budget_eur_per_person" in arguments.model_fields_set:
            changes["budget_eur"] = arguments.budget_eur_per_person
        if arguments.shift_dates and "starts_on" in changes and "ends_on" not in changes:
            changes["ends_on"] = current.ends_on + (changes["starts_on"] - current.starts_on)
        request = travel.TripIn(
            **{
                "title": current.title,
                "starts_on": current.starts_on,
                "ends_on": current.ends_on,
                "travellers": current.travellers,
                "companions": current.companions,
                "tags": current.tags,
                "notes": current.notes,
                **changes,
            }
        )
        return await travel.update_trip(
            connection, trip_id, request, arguments.keep_group_total, arguments.shift_dates
        )

    return await _edit(connection, run, arguments.dry_run)


async def confirm_trip(connection: AsyncConnection, arguments: TripRef) -> dict[str, Any]:
    return await _edit(
        connection, lambda: travel.set_status(connection, str(arguments.trip_id), "confirmed")
    )


async def unconfirm_trip(connection: AsyncConnection, arguments: TripRef) -> dict[str, Any]:
    return await _edit(
        connection, lambda: travel.set_status(connection, str(arguments.trip_id), "plan")
    )


async def archive_trip(connection: AsyncConnection, arguments: TripRef) -> dict[str, Any]:
    return await _edit(
        connection, lambda: travel.archive_trip(connection, str(arguments.trip_id), True)
    )


async def unarchive_trip(connection: AsyncConnection, arguments: TripRef) -> dict[str, Any]:
    return await _edit(
        connection, lambda: travel.archive_trip(connection, str(arguments.trip_id), False)
    )


class DeleteTrip(TripRef):
    title: str = Field(
        min_length=1,
        max_length=120,
        description="El título exacto del viaje, como lo da get_trip. Si no coincide, no se borra "
        "nada.",
    )
    dry_run: bool = DRY_RUN


async def delete_trip(connection: AsyncConnection, arguments: DeleteTrip) -> dict[str, Any]:
    trip_id = str(arguments.trip_id)

    async def run() -> dict[str, Any]:
        found = await travel.trip(connection, trip_id)
        if arguments.title != found.title:
            raise travel.Conflict(
                f"ese viaje se llama «{found.title}», no «{arguments.title}»; no he borrado nada",
                "TITLE_MISMATCH",
                [{"trip_id": found.id, "title": found.title}],
            )
        await travel.delete_trip(connection, trip_id)
        return {
            "deleted": {
                "trip_id": found.id,
                "title": found.title,
                "stays": len(found.stays),
                "visits": len(found.visits),
                "legs": len(found.legs),
                "expenses": len(found.expenses),
            }
        }

    return await _mutate(connection, run, arguments.dry_run)


class ShareTrip(TripRef):
    space: str | None = Field(
        min_length=1,
        max_length=80,
        description="El nombre del espacio de arga con el que compartirlo, o null para que vuelva "
        "a ser solo tuyo.",
    )


async def _spaces(connection: AsyncConnection) -> list[dict]:
    try:
        found = await spaces.of_caller()
    except spaces.Unavailable as error:
        raise travel.Conflict(f"no sé tus espacios: {error}", "UNAVAILABLE") from error
    ids = tuple(UUID(space["id"]) for space in found)
    await connection.execute(
        text("select set_config(:guc, :spaces, true)"),
        {"guc": SPACES_GUC, "spaces": "{" + format_spaces(ids) + "}"},
    )
    return found


async def share_trip(connection: AsyncConnection, arguments: ShareTrip) -> dict[str, Any]:
    async def run() -> travel.Trip:
        space_id = None
        if arguments.space is not None:
            wanted = arguments.space.strip().lower()
            mine = await _spaces(connection)
            match = [one for one in mine if one["name"].strip().lower() == wanted]
            if not match:
                raise travel.Conflict(
                    f"no estás en ningún espacio llamado «{arguments.space}»",
                    "NOT_FOUND",
                    [{"space": one["name"]} for one in mine],
                )
            space_id = match[0]["id"]
        return await travel.share_trip(connection, str(arguments.trip_id), space_id)

    return await _edit(connection, run)
