from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_nutrients
from macros import (
    detail,
    expenditure,
    goals,
    intake,
    meals,
    pantry,
    reruns,
    suggestions,
    summary,
    templates,
    usual,
)
from macros.common import MADRID, Conflict, NotFound, Unavailable, now, today

MODULE = "macros"
WRITE_ROLE = f"mod_{MODULE}"
READ_ROLE = f"mod_{MODULE}_read"


def role_for_scopes(scopes: set[str]) -> str | None:
    if f"{MODULE}:write" in scopes:
        return WRITE_ROLE
    if f"{MODULE}:read" in scopes:
        return READ_ROLE
    return None


def _short(values: dict[str, float]) -> dict[str, float]:
    return {key: round(values[key], 1) for key in arga_nutrients.MACROS if key in values}


def _entry(entry: intake.Entry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "time": entry.eaten_at.astimezone(MADRID).strftime("%H:%M"),
        "day": entry.day.isoformat(),
        "meal": entry.meal,
        "said": entry.said,
        "items": [
            {
                "item_id": item.id,
                "name": item.name,
                "kind": item.kind,
                "quantity": item.quantity,
                "unit": item.unit,
                **({"portion": item.portion} if item.portion else {}),
                **({"doubt": item.doubt} if item.doubt else {}),
                "estimated": item.estimated,
                **_short(item.nutrients),
            }
            for item in entry.items
        ],
    }


class FindFood(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=60,
        description="Una sola cosa, como se diría: `café`, `leche semidesnatada`, `lentejas`.",
    )


LAST_TIME = text("""
    select i.name, i.quantity, i.unit, i.food_id, i.recipe_id
    from macros.macros_item i join macros.macros_entry e on e.id = i.entry_id
    where lower(i.name) like '%' || lower(:query) || '%'
    order by e.eaten_at desc
    limit 3
""")


async def find_food(
    connection: AsyncConnection, arguments: FindFood, client: httpx.AsyncClient
) -> dict[str, Any]:
    query = arguments.query.strip()
    found = await pantry.search(client, query)
    recipes = await pantry.recipes(client, query)
    last = (await connection.execute(LAST_TIME, {"query": query})).all()
    return {
        "pantry": [
            {
                "food_id": one["id"],
                "name": one["label"],
                "per_100g": _short(one["nutrients"]),
                "grams_per_unit": one.get("grams_per_unit"),
                "portions": one.get("portions") or {},
                "edible_fraction": one.get("edible_fraction"),
                "per_unit": one.get("unit_name") if one.get("nutrients_per") == "unit" else None,
            }
            for one in found["foods"]
        ],
        "recipes": [
            {"recipe_id": one["id"], "name": one["name"], "servings": one["servings"]}
            for one in recipes
        ],
        "outside": [
            {
                "source": one["source"],
                "source_ref": one["source_ref"],
                "name": one["name"],
                "brand": one.get("brand"),
                "per_100g": _short(one["nutrients"]),
            }
            for one in found.get("candidates", [])
        ],
        "outside_failed": found.get("failed", []),
        "last_time": [
            {"name": row.name, "quantity": float(row.quantity), "unit": row.unit} for row in last
        ],
    }


class GetDay(BaseModel):
    day: date | None = Field(default=None, description="Sin fecha, hoy.")
    nutrient: str | None = Field(
        default=None,
        min_length=2,
        max_length=40,
        description=(
            "Con una clave de nutriente (`sugars`, `sodium`…, o `omega3_epa_dha` o `water`), "
            "además qué de lo comido lo pone, de más a menos (`contributors`)."
        ),
    )


async def get_day(connection: AsyncConnection, arguments: GetDay) -> dict[str, Any]:
    found = await summary.day(connection, arguments.day or today())
    return {
        "day": found.day.isoformat(),
        "totals": {key: round(value, 1) for key, value in found.nutrients.items()},
        "target": None if found.target is None else found.target.model_dump(mode="json"),
        "remaining": found.remaining,
        "drinks": found.drinks.model_dump(),
        "entries": [_entry(entry) for entry in found.entries],
        "meals": [
            {
                "meal": one.meal,
                "label": one.label,
                "usual_at": one.usual_at,
                "kcal": one.kcal,
                "protein": one.protein,
                "entry_ids": one.entry_ids,
                "planned_ids": one.planned_ids,
            }
            for one in found.meals
        ],
        "planned": [_entry(entry) for entry in found.planned],
        "day_kind": None if found.day_kind is None else found.day_kind.model_dump(mode="json"),
        "goals": [_goal_state(one) for one in found.goals],
        "complete": found.complete,
        "caffeine": None
        if found.caffeine is None
        else {
            "total_mg": found.caffeine.total_mg,
            "last_at": None
            if found.caffeine.last_at is None
            else found.caffeine.last_at.isoformat(timespec="minutes"),
            "in_body_now_mg": found.caffeine.now_mg,
        },
        "partial": sorted(
            item.key for group in found.groups for item in group.items if item.partial
        ),
        **({} if arguments.nutrient is None else _contributors(found.entries, arguments.nutrient)),
    }


def _contributors(entries: list[intake.Entry], nutrient: str) -> dict[str, Any]:
    try:
        ranked = detail.contributors(entries, nutrient)
    except ValueError as error:
        return {"contributors": None, "note": str(error)}
    return {"contributors": ranked.model_dump()}


def _goal_state(one: goals.GoalState) -> dict[str, Any]:
    return {
        "nutrient": one.nutrient,
        "value": one.value,
        "nutrient_unit": one.unit,
        "goal": {"min": one.min, "max": one.max, "unit": one.basis},
        "share_of_kcal": one.share,
        "status": one.status,
        "source": one.source,
        "profile": one.profile,
        "coverage": one.coverage,
        **({"per_kg": one.per_kg.model_dump()} if one.per_kg else {}),
    }


class GetGoals(BaseModel):
    day: date | None = Field(default=None, description="Sin fecha, hoy.")


async def get_goals(connection: AsyncConnection, arguments: GetGoals) -> dict[str, Any]:
    return await goals.current(connection, arguments.day)


class SetGoal(goals.GoalIn):
    pass


async def set_goal(connection: AsyncConnection, arguments: SetGoal) -> dict[str, Any]:
    return await goals.set_goal(connection, goals.GoalIn(**arguments.model_dump()))


class SetDayKind(BaseModel):
    day: date | None = Field(default=None, description="Sin fecha, hoy.")
    kind: Literal["training", "rest"] | None = Field(
        description=(
            "`training` o `rest`; null vuelve a decidirlo solo (un entreno ese día es entreno)."
        )
    )


async def set_day_kind(connection: AsyncConnection, arguments: SetDayKind) -> dict[str, Any]:
    found = await goals.set_day_kind(connection, arguments.day or today(), arguments.kind)
    return {"day_kind": found.model_dump(mode="json")}


class MarkDayComplete(BaseModel):
    day: date | None = Field(default=None, description="Sin fecha, hoy.")
    complete: bool = Field(
        default=True, description="`false` lo deja como no completo: algo quedó sin apuntar."
    )


async def mark_day_complete(
    connection: AsyncConnection, arguments: MarkDayComplete
) -> dict[str, Any]:
    day = arguments.day or today()
    done = await expenditure.mark(connection, day, arguments.complete, today())
    return {"day": day.isoformat(), "complete": done}


class GetWeek(BaseModel):
    last: date | None = Field(default=None, description="El último de los siete días; hoy.")
    all_micros: bool = Field(
        default=False, description="Todos los micronutrientes, no solo los de portada."
    )
    only_complete: bool = Field(
        default=True,
        description=(
            "Las medias, de los días marcados completos (si hay 3 o más)."
            " Con `false`, de todos los días con algo apuntado."
        ),
    )


class GetSuggestions(BaseModel):
    last: date | None = Field(default=None, description="El último de los siete días; hoy.")


async def get_suggestions(connection: AsyncConnection, arguments: GetSuggestions) -> dict[str, Any]:
    found = await suggestions.suggest(connection, arguments.last or today())
    return found.model_dump(mode="json")


async def get_week(connection: AsyncConnection, arguments: GetWeek) -> dict[str, Any]:
    found = await summary.week(
        connection, arguments.last or today(), arguments.all_micros, arguments.only_complete
    )
    return {
        "from": found.first.isoformat(),
        "to": found.last.isoformat(),
        "days_logged": found.days_logged,
        "counted": None if found.counted is None else found.counted.model_dump(),
        "daily_average": {key: round(value, 1) for key, value in found.averages.items()},
        "days": [mark.model_dump(mode="json") for mark in found.days],
        "drinks_daily_average": found.drinks.model_dump(),
        "profile": found.profile.model_dump(),
        "micros": [
            {
                "nutrient": micro.name,
                "unit": micro.unit,
                "daily_average": None if micro.value is None else round(micro.value, 2),
                "reference": None
                if micro.reference is None
                else {"kind": micro.reference.kind, "value": micro.reference.value},
                "status": micro.status,
                "coverage": micro.coverage,
                "partial": micro.partial,
                "missing_data_in": micro.missing,
            }
            for micro in found.micros
        ],
        "expenditure": None
        if found.expenditure is None
        else {
            **found.expenditure.model_dump(mode="json"),
            "proposals": [
                {**one.model_dump(), "said": expenditure.proposal_label(one)}
                for one in found.expenditure.proposals
            ],
        },
    }


class LogIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eaten_at: datetime | None = Field(
        default=None, description="Cuándo, con zona. Sin ella, ahora."
    )
    meal: meals.Meal | None = Field(
        default=None,
        description=(
            "La comida: breakfast, morning, lunch, snack, dinner o night. Sin `eaten_at`, va a su "
            "hora de siempre hoy (o ahora, si es la de ahora); con `eaten_at`, ese día, y a esa "
            "hora si cae en ella."
        ),
    )
    said: str | None = Field(
        default=None, max_length=1000, description="La frase tal como la dijo la persona."
    )
    items: list[intake.ItemIn] = Field(min_length=1, max_length=intake.MAX_ITEMS)
    planned: bool = Field(
        default=False,
        description=(
            "Lo que aún no se ha comido (la cena de esta noche): queda planificado y no suma "
            "hasta `confirm_intake`."
        ),
    )


async def log_intake(
    connection: AsyncConnection, arguments: LogIntake, client: httpx.AsyncClient
) -> dict[str, Any]:
    entry = await intake.log(
        connection,
        client,
        intake.EntryIn(
            eaten_at=arguments.eaten_at,
            meal=arguments.meal,
            said=arguments.said,
            items=arguments.items,
            planned=arguments.planned,
        ),
        origin="claude",
    )
    return {"logged": _entry(entry), "totals": _short(entry.nutrients)}


class ConfirmIntake(BaseModel):
    entry_id: str = Field(description="La entrada planificada, tal cual la da `get_day`.")
    eaten_at: datetime | None = Field(
        default=None, description="Cuándo se comió, con zona. Sin ella, a la hora planificada."
    )


async def confirm_intake(connection: AsyncConnection, arguments: ConfirmIntake) -> dict[str, Any]:
    entry = await intake.confirm(connection, arguments.entry_id, arguments.eaten_at)
    return {"confirmed": _entry(entry), "totals": _short(entry.nutrients)}


class SaveTemplate(templates.TemplateIn):
    pass


async def save_template(connection: AsyncConnection, arguments: SaveTemplate) -> dict[str, Any]:
    found = await templates.save(connection, templates.TemplateIn(**arguments.model_dump()))
    return {"template": found.model_dump(mode="json")}


class GetUsual(BaseModel):
    meal: meals.Meal | None = Field(default=None, description="La comida; sin ella, la de ahora.")
    day: date | None = Field(default=None, description="Sin fecha, hoy.")


async def get_usual(connection: AsyncConnection, arguments: GetUsual) -> dict[str, Any]:
    meal = arguments.meal or meals.meal_of(now())
    found = await usual.usual(connection, meal, arguments.day or today())
    return found.model_dump(mode="json")


class RepeatIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ids: list[str] = Field(default_factory=list, max_length=intake.MAX_ITEMS)
    entry_ids: list[str] = Field(default_factory=list, max_length=intake.MAX_ITEMS)
    from_day: date | None = Field(default=None, description="El día de la comida que se repite.")
    from_meal: meals.Meal | None = None
    meal: meals.Meal | None = Field(
        default=None, description="A qué comida; sin ella, a la misma de donde sale."
    )
    day: date | None = Field(default=None, description="A qué día; sin él, hoy.")

    @model_validator(mode="after")
    def _one_source(self) -> RepeatIntake:
        given = [bool(self.item_ids), bool(self.entry_ids), self.from_day is not None]
        if sum(given) != 1:
            raise ValueError("una fuente: item_ids, entry_ids, o from_day con from_meal")
        if self.from_day is not None and self.from_meal is None:
            raise ValueError("from_day va con from_meal")
        return self


async def repeat_intake(connection: AsyncConnection, arguments: RepeatIntake) -> dict[str, Any]:
    if arguments.from_day is not None and arguments.from_meal is not None:
        entry = await intake.repeat_meal(
            connection,
            arguments.from_day,
            arguments.from_meal,
            arguments.day,
            arguments.meal,
            "claude",
        )
    else:
        items = arguments.item_ids or await intake.items_of_entries(connection, arguments.entry_ids)
        entry = await intake.repeat_items(
            connection, items, arguments.meal, arguments.day, None, "claude"
        )
    return {"logged": _entry(entry), "totals": _short(entry.nutrients)}


class LogTemplate(BaseModel):
    template: str = Field(
        min_length=1, max_length=80, description="El nombre de la plantilla, o su id."
    )
    eaten_at: datetime | None = Field(
        default=None, description="Cuándo, con zona; sin ella, ahora."
    )
    planned: bool = Field(default=False, description="Planificada en vez de comida.")


async def log_template(
    connection: AsyncConnection, arguments: LogTemplate, client: httpx.AsyncClient
) -> dict[str, Any]:
    template = await templates.find(connection, arguments.template)
    entry = await templates.use(
        connection, client, template, arguments.eaten_at, arguments.planned, "claude"
    )
    return {"logged": _entry(entry), "totals": _short(entry.nutrients)}


class DeleteTemplate(BaseModel):
    template_id: str = Field(min_length=36, max_length=36)


async def delete_template(connection: AsyncConnection, arguments: DeleteTemplate) -> dict[str, Any]:
    await templates.remove(connection, arguments.template_id)
    return {"deleted": arguments.template_id}


class GetOutdatedRecipes(BaseModel):
    pass


async def get_outdated_recipes(
    connection: AsyncConnection, arguments: GetOutdatedRecipes, client: httpx.AsyncClient
) -> dict[str, Any]:
    found = await reruns.outdated(connection, client)
    return {"recipes": [one.model_dump(mode="json") for one in found]}


class RecalculateRecipeIntakes(BaseModel):
    recipe_id: str = Field(min_length=36, max_length=36)


async def recalculate_recipe_intakes(
    connection: AsyncConnection, arguments: RecalculateRecipeIntakes, client: httpx.AsyncClient
) -> dict[str, Any]:
    return {"recalculated": await reruns.recalculate(connection, client, arguments.recipe_id)}


class UpdateIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    eaten_at: datetime | None = None
    meal: meals.Meal | None = Field(
        default=None, description="Pasarla a otra comida del mismo día, a su hora de siempre."
    )
    change: list[intake.ItemChange] = Field(default_factory=list)
    add: list[intake.ItemIn] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list, description="item_id de las líneas fuera.")


async def update_intake(
    connection: AsyncConnection, arguments: UpdateIntake, client: httpx.AsyncClient
) -> dict[str, Any]:
    entry = await intake.update(
        connection,
        client,
        arguments.entry_id,
        intake.EntryPatch(
            eaten_at=arguments.eaten_at,
            meal=arguments.meal,
            change=arguments.change,
            add=arguments.add,
            remove=arguments.remove,
        ),
    )
    return {"updated": _entry(entry)}


class DeleteIntake(BaseModel):
    entry_id: str | None = None
    item_id: str | None = None

    @model_validator(mode="after")
    def _one(self) -> DeleteIntake:
        if bool(self.entry_id) == bool(self.item_id):
            raise ValueError("o entry_id o item_id, uno de los dos")
        return self


async def delete_intake(connection: AsyncConnection, arguments: DeleteIntake) -> dict[str, Any]:
    if arguments.entry_id:
        await intake.delete_entry(connection, arguments.entry_id)
        return {"deleted": "entry"}
    left = await intake.delete_item(connection, arguments.item_id or "")
    return {"deleted": "item", "entry_left": None if left is None else _entry(left)}


async def set_target(connection: AsyncConnection, arguments: summary.TargetIn) -> dict[str, Any]:
    found = await summary.set_target(connection, arguments)
    return {"target": found.model_dump(mode="json")}


@dataclass(frozen=True)
class Tool:
    arguments: type[BaseModel]
    run: Callable[..., Awaitable[dict[str, Any]]]
    asks_pantry: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "run", _told(self.run))

    @property
    def asks_the_hub(self) -> bool:
        return self.asks_pantry


def _told(
    run: Callable[..., Awaitable[dict[str, Any]]],
) -> Callable[..., Awaitable[dict[str, Any]]]:

    async def told(
        connection: AsyncConnection, arguments: BaseModel, **extra: Any
    ) -> dict[str, Any]:
        try:
            async with connection.begin_nested():
                return await run(connection, arguments, **extra)
        except (NotFound, Conflict, Unavailable) as error:
            return {"error": str(error)}

    return told


TOOLS: dict[str, Tool] = {
    "find_food": Tool(FindFood, find_food, asks_pantry=True),
    "get_day": Tool(GetDay, get_day),
    "get_week": Tool(GetWeek, get_week),
    "get_suggestions": Tool(GetSuggestions, get_suggestions),
    "log_intake": Tool(LogIntake, log_intake, asks_pantry=True),
    "update_intake": Tool(UpdateIntake, update_intake, asks_pantry=True),
    "delete_intake": Tool(DeleteIntake, delete_intake),
    "set_target": Tool(summary.TargetIn, set_target),
    "get_goals": Tool(GetGoals, get_goals),
    "set_goal": Tool(SetGoal, set_goal),
    "set_day_kind": Tool(SetDayKind, set_day_kind),
    "mark_day_complete": Tool(MarkDayComplete, mark_day_complete),
    "confirm_intake": Tool(ConfirmIntake, confirm_intake),
    "save_template": Tool(SaveTemplate, save_template),
    "get_usual": Tool(GetUsual, get_usual),
    "repeat_intake": Tool(RepeatIntake, repeat_intake),
    "log_template": Tool(LogTemplate, log_template, asks_pantry=True),
    "delete_template": Tool(DeleteTemplate, delete_template),
    "get_outdated_recipes": Tool(GetOutdatedRecipes, get_outdated_recipes, asks_pantry=True),
    "recalculate_recipe_intakes": Tool(
        RecalculateRecipeIntakes, recalculate_recipe_intakes, asks_pantry=True
    ),
}
