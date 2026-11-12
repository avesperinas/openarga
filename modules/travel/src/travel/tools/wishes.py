from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from travel import (
    ideas,
    travel,
)
from travel.tools.common import (
    DRY_RUN,
    PlaceArgument,
    _edit,
    _given,
    _mutate,
    _no_null,
    _place,
    _resolve,
)
from travel.tools.trips import _spaces

MONTH_NAMES = (
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
)


def _idea(found: ideas.Idea) -> dict[str, Any]:
    return {
        "idea_id": found.id,
        "title": found.title,
        "notes": found.notes,
        "budget_eur_per_person": found.budget_eur,
        "days": {"min": found.days_min, "max": found.days_max},
        "months": [MONTH_NAMES[month - 1] for month in found.months],
        "tags": found.tags,
        "archived": found.archived,
        "destinations": [
            {"idea_place_id": one.id, **_place(one.place), "note": one.note} for one in found.places
        ],
        "countries": found.countries,
        "trips": [
            {
                "trip_id": one.id,
                "title": one.title,
                "starts_on": one.starts_on.isoformat(),
                "phase": one.phase,
            }
            for one in found.trips
        ],
        "shared": found.space_id is not None,
        "mine": found.mine,
    }


class GetIdeas(BaseModel):
    include_archived: bool = False


async def get_ideas(connection: AsyncConnection, arguments: GetIdeas) -> dict[str, Any]:
    found = [
        one
        for one in await ideas.ideas(connection)
        if arguments.include_archived or not one.archived
    ]
    return {"total": len(found), "ideas": [_idea(one) for one in found]}


MONTHS = Field(
    default=None,
    description="Los meses buenos para ir, del 1 al 12: [4, 5, 10] es abril, mayo y octubre.",
)


class CreateIdea(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    destinations: list[PlaceArgument] = Field(
        default=[], max_length=30, description="Candidatos de find_place o place_id guardados."
    )
    budget_eur_per_person: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    days_min: int | None = Field(default=None, ge=1, le=365)
    days_max: int | None = Field(default=None, ge=1, le=365)
    months: list[int] | None = MONTHS
    tags: list[str] = Field(default=[], max_length=20)
    notes: str | None = Field(default=None, max_length=4000)


async def create_idea(connection: AsyncConnection, arguments: CreateIdea) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        found = await ideas.create_idea(
            connection,
            ideas.IdeaIn(
                title=arguments.title,
                notes=arguments.notes,
                budget_eur=arguments.budget_eur_per_person,
                days_min=arguments.days_min,
                days_max=arguments.days_max,
                months=arguments.months or [],
                tags=arguments.tags,
            ),
            source="tool",
        )
        for destination in arguments.destinations:
            place = await _resolve(connection, destination)
            found = await ideas.add_place(connection, found.id, place.id)
        return {"idea": _idea(found)}

    return await _mutate(connection, run)


class IdeaRef(BaseModel):
    idea_id: UUID


class UpdateIdea(IdeaRef):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    budget_eur_per_person: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    days_min: int | None = Field(default=None, ge=1, le=365)
    days_max: int | None = Field(default=None, ge=1, le=365)
    months: list[int] | None = Field(default=None, description="La lista entera, del 1 al 12.")
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=4000, description="`null` las borra.")


async def update_idea(connection: AsyncConnection, arguments: UpdateIdea) -> dict[str, Any]:
    idea_id = str(arguments.idea_id)

    async def run() -> dict[str, Any]:
        _no_null(arguments, "title")
        current = await ideas.idea(connection, idea_id)
        changes = _given(arguments, "title", "days_min", "days_max", "months", "tags", "notes")
        if "budget_eur_per_person" in arguments.model_fields_set:
            changes["budget_eur"] = arguments.budget_eur_per_person
        for listed in ("months", "tags"):
            if listed in changes and changes[listed] is None:
                changes[listed] = []
        request = ideas.IdeaIn(
            **{
                "title": current.title,
                "notes": current.notes,
                "budget_eur": current.budget_eur,
                "days_min": current.days_min,
                "days_max": current.days_max,
                "months": current.months,
                "tags": current.tags,
                **changes,
            }
        )
        return {"idea": _idea(await ideas.update_idea(connection, idea_id, request))}

    return await _mutate(connection, run)


class AddIdeaPlace(IdeaRef):
    place: PlaceArgument
    note: str | None = Field(default=None, max_length=500)


async def add_idea_place(connection: AsyncConnection, arguments: AddIdeaPlace) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        place = await _resolve(connection, arguments.place)
        found = await ideas.add_place(connection, str(arguments.idea_id), place.id, arguments.note)
        return {"idea": _idea(found)}

    return await _mutate(connection, run)


class RemoveIdeaPlace(IdeaRef):
    idea_place_id: UUID


async def remove_idea_place(
    connection: AsyncConnection, arguments: RemoveIdeaPlace
) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        found = await ideas.remove_place(
            connection, str(arguments.idea_id), str(arguments.idea_place_id)
        )
        return {"idea": _idea(found)}

    return await _mutate(connection, run)


async def archive_idea(connection: AsyncConnection, arguments: IdeaRef) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        return {"idea": _idea(await ideas.archive_idea(connection, str(arguments.idea_id), True))}

    return await _mutate(connection, run)


async def unarchive_idea(connection: AsyncConnection, arguments: IdeaRef) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        found = await ideas.archive_idea(connection, str(arguments.idea_id), False)
        return {"idea": _idea(found)}

    return await _mutate(connection, run)


class DeleteIdea(IdeaRef):
    title: str = Field(
        min_length=1, max_length=120, description="El título exacto: si no coincide, no se borra."
    )
    dry_run: bool = DRY_RUN


async def delete_idea(connection: AsyncConnection, arguments: DeleteIdea) -> dict[str, Any]:
    idea_id = str(arguments.idea_id)

    async def run() -> dict[str, Any]:
        found = await ideas.idea(connection, idea_id)
        if arguments.title != found.title:
            raise travel.Conflict(
                f"esa idea se llama «{found.title}», no «{arguments.title}»; no he borrado nada",
                "TITLE_MISMATCH",
                [{"idea_id": found.id, "title": found.title}],
            )
        await ideas.delete_idea(connection, idea_id)
        return {
            "deleted": {
                "idea_id": found.id,
                "title": found.title,
                "destinations": len(found.places),
            }
        }

    return await _mutate(connection, run, arguments.dry_run)


class PlanIdea(IdeaRef):
    starts_on: date
    ends_on: date
    title: str | None = Field(
        default=None, min_length=1, max_length=120, description="Sin darlo, el de la idea."
    )
    travellers: int = Field(default=1, ge=1, le=50)


async def plan_idea(connection: AsyncConnection, arguments: PlanIdea) -> dict[str, Any]:
    async def run() -> travel.Trip:
        if arguments.ends_on < arguments.starts_on:
            raise travel.Conflict("el viaje no puede acabar antes de empezar", "INVALID")
        return await ideas.plan_idea(
            connection,
            str(arguments.idea_id),
            arguments.starts_on,
            arguments.ends_on,
            arguments.title,
            arguments.travellers,
        )

    return await _edit(connection, run)


class ShareIdea(IdeaRef):
    space: str | None = Field(
        min_length=1,
        max_length=80,
        description="El nombre del espacio de arga, o null para que vuelva a ser solo tuya.",
    )


async def share_idea(connection: AsyncConnection, arguments: ShareIdea) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
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
        return {"idea": _idea(await ideas.share_idea(connection, str(arguments.idea_id), space_id))}

    return await _mutate(connection, run)
