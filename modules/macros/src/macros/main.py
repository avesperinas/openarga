from __future__ import annotations

import hmac
import os
from datetime import date, datetime, time
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
import arga_nutrients
from arga_module.service import INSUFFICIENT_PRIVILEGE, Service
from arga_tenancy import require_person
from macros import (
    detail,
    expenditure,
    goals,
    intake,
    meals,
    notices,
    pantry,
    publisher,
    reruns,
    suggestions,
    summary,
    templates,
    tools,
    usual,
    weight,
    widgets,
)
from macros import panel as home_panel
from macros.common import Conflict, NotFound, Unavailable, today

MODULE_ID = "macros"

service = Service(
    MODULE_ID,
    "Macros",
    tools=tools.TOOLS,
    role_for_scopes=tools.role_for_scopes,
    widgets=widgets.RENDERERS,
    panel=home_panel.build,
    publisher=publisher.PUBLISHER,
    ui_dist=Path(__file__).resolve().parents[2] / "ui" / "dist",
)
app = service.app
as_app = service.as_app


def client() -> httpx.AsyncClient:
    return service.client()


async def _edit(action, *args):
    try:
        async with as_app() as connection:
            return await action(connection, *args)
    except NotFound as error:
        raise HTTPException(status_code=404, detail=f"no existe: {error}") from error
    except Conflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
            raise HTTPException(status_code=403, detail="no puedes hacer esto aquí") from error
        raise


@app.get("/weight")
async def read_weight() -> weight.History:
    return await _edit(weight.history)


@app.post("/weight")
async def log_weight(body: weight.WeightIn) -> weight.History:
    try:
        logged = await weight.log(client(), body)
    except Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return weight.with_logged(await _edit(weight.history), logged)


@app.get("/day")
async def read_day(day: date | None = None) -> summary.Day:
    return await _edit(summary.day, day or today())


@app.get("/week")
async def read_week(
    last: date | None = None,
    all: bool = False,  # noqa: A002
    only_complete: bool = True,
) -> summary.Week:
    return await _edit(summary.week, last or today(), all, only_complete)


@app.get("/week/trend")
async def read_trend(
    last: date | None = None, weeks: int = Query(default=8, ge=1, le=26)
) -> summary.Trend:
    return await _edit(summary.trend, last or today(), weeks)


@app.get("/week/suggestions")
async def read_suggestions(last: date | None = None) -> suggestions.Suggestions:
    return await _edit(suggestions.suggest, last or today())


@app.get("/week/contributors/{nutrient}")
async def read_week_contributors(nutrient: str, last: date | None = None) -> dict:
    return await _edit(suggestions.contributors, nutrient, last or today())


@app.get("/search")
async def search(q: str = Query(min_length=2, max_length=60), outside: bool = True) -> dict:
    try:
        found = await pantry.search(client(), q.strip(), outside)
        recipes = await pantry.recipes(client(), q.strip())
    except Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {**found, "recipes": recipes}


@app.post("/entries", status_code=201)
async def create_entry(body: intake.EntryIn) -> intake.Entry:
    return await _edit(lambda connection: intake.log(connection, client(), body, "app"))


@app.get("/entries/{entry_id}")
async def read_entry(entry_id: UUID) -> intake.Entry:
    return await _edit(intake.one, str(entry_id))


@app.patch("/entries/{entry_id}")
async def update_entry(entry_id: UUID, body: intake.EntryPatch) -> intake.Entry:
    return await _edit(lambda connection: intake.update(connection, client(), str(entry_id), body))


@app.delete("/entries/{entry_id}", status_code=204)
async def delete_entry(entry_id: UUID) -> Response:
    await _edit(intake.delete_entry, str(entry_id))
    return Response(status_code=204)


@app.post("/entries/{entry_id}/repeat", status_code=201)
async def repeat_entry(entry_id: UUID) -> intake.Entry:
    return await _edit(intake.repeat, str(entry_id))


class ConfirmBody(BaseModel):
    eaten_at: datetime | None = None


@app.post("/entries/{entry_id}/confirm")
async def confirm_entry(entry_id: UUID, body: ConfirmBody) -> intake.Entry:
    return await _edit(intake.confirm, str(entry_id), body.eaten_at)


class DishRename(BaseModel):
    model_config = {"populate_by_name": True}

    old: str = Field(alias="from", min_length=1, max_length=120)
    new: str | None = Field(default=None, alias="to", max_length=120)


@app.put("/entries/{entry_id}/dish")
async def rename_dish(entry_id: UUID, body: DishRename) -> intake.Entry:
    return await _edit(intake.rename_dish, str(entry_id), body.old, body.new)


class DishRecipe(BaseModel):
    dish: str = Field(min_length=1, max_length=120)


@app.post("/entries/{entry_id}/dish/recipe")
async def dish_to_recipe(entry_id: UUID, body: DishRecipe) -> dict:
    entry = await _edit(intake.one, str(entry_id))
    lines = [item for item in entry.items if item.dish == body.dish]
    if not lines:
        raise HTTPException(status_code=404, detail=f"No hay un plato «{body.dish}» en esa entrada")
    foods = [
        item
        for item in lines
        if item.kind == "food" and item.food_id and item.unit in ("g", "ml", "unit")
    ]
    if not foods:
        raise HTTPException(
            status_code=409, detail="Ese plato no tiene alimentos de la despensa que guardar"
        )
    ingredients = [
        {
            "food_id": item.food_id,
            "quantity": item.quantity,
            "unit": item.unit,
            **({"portion": item.portion} if item.portion else {}),
        }
        for item in foods
    ]
    try:
        created = await pantry.create_recipe(client(), body.dish, ingredients)
    except Unavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {**created, "skipped": len(lines) - len(foods)}


@app.post("/entries/{entry_id}/unconfirm")
async def unconfirm_entry(entry_id: UUID) -> intake.Entry:
    return await _edit(intake.unconfirm, str(entry_id))


class RepeatMeal(BaseModel):
    from_day: date
    meal: meals.Meal
    day: date | None = None
    to_meal: meals.Meal | None = None


@app.post("/meals/repeat", status_code=201)
async def repeat_meal(body: RepeatMeal) -> intake.Entry:
    return await _edit(intake.repeat_meal, body.from_day, body.meal, body.day, body.to_meal)


@app.get("/usual/{meal}")
async def read_usual_of(meal: meals.Meal, day: date | None = None) -> usual.Usual:
    return await _edit(usual.usual, meal, day or today())


class RepeatItems(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=intake.MAX_ITEMS)
    meal: meals.Meal | None = None
    day: date | None = None


@app.post("/items/repeat", status_code=201)
async def repeat_items(body: RepeatItems) -> intake.Entry:
    return await _edit(intake.repeat_items, body.item_ids, body.meal, body.day)


class MealTime(BaseModel):
    at: time


@app.put("/meals/{day}/{meal}/time")
async def move_meal(day: date, meal: meals.Meal, body: MealTime) -> list[intake.Entry]:
    return await _edit(intake.move_meal, day, meal, body.at.replace(second=0, microsecond=0))


@app.delete("/meals/{day}/{meal}", status_code=204)
async def delete_meal(day: date, meal: meals.Meal) -> Response:
    await _edit(intake.delete_meal, day, meal)
    return Response(status_code=204)


class MoveItem(BaseModel):
    meal: meals.Meal


@app.post("/items/{item_id}/move")
async def move_item(item_id: UUID, body: MoveItem) -> intake.Entry:
    return await _edit(intake.move_item, str(item_id), body.meal)


class FromMeal(BaseModel):
    day: date
    meal: meals.Meal
    name: str = Field(min_length=1, max_length=80)
    daily_at: time | None = None


@app.post("/templates/from-meal", status_code=201)
async def template_from_meal(body: FromMeal) -> templates.Template:
    return await _edit(templates.from_meal, body.day, body.meal, body.name, body.daily_at)


@app.get("/templates")
async def read_templates() -> list[templates.Template]:
    return await _edit(templates.all_of)


@app.post("/templates", status_code=201)
async def save_template(body: templates.TemplateIn) -> templates.Template:
    return await _edit(templates.save, body)


class FromEntry(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    daily_at: time | None = None


@app.post("/templates/from-entry/{entry_id}", status_code=201)
async def template_from_entry(entry_id: UUID, body: FromEntry) -> templates.Template:
    return await _edit(templates.from_entry, str(entry_id), body.name, body.daily_at)


class UseBody(BaseModel):
    eaten_at: datetime | None = None
    planned: bool = False
    meal: meals.Meal | None = None


@app.post("/templates/{template_id}/log", status_code=201)
async def log_template(template_id: UUID, body: UseBody) -> intake.Entry:
    async def logged(connection: AsyncConnection) -> intake.Entry:
        found = await templates.read(connection, str(template_id))
        eaten_at = body.eaten_at
        if body.meal is not None:
            eaten_at = await meals.moment_for(connection, body.meal, None, eaten_at)
        return await templates.use(connection, client(), found, eaten_at, body.planned)

    return await _edit(logged)


@app.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: UUID) -> Response:
    await _edit(templates.remove, str(template_id))
    return Response(status_code=204)


@app.get("/recipes/outdated")
async def read_outdated() -> list[reruns.Outdated]:
    return await _edit(lambda connection: reruns.outdated(connection, client()))


@app.post("/recipes/{recipe_id}/recalculate")
async def recalculate(recipe_id: UUID) -> dict:
    return await _edit(lambda connection: reruns.recalculate(connection, client(), str(recipe_id)))


@app.delete("/items/{item_id}")
async def delete_item(item_id: UUID) -> dict:
    left = await _edit(intake.delete_item, str(item_id))
    return {"entry": None if left is None else left.model_dump(mode="json")}


@app.post("/items/{item_id}/sure")
async def item_is_sure(item_id: UUID) -> intake.Entry:
    return await _edit(intake.clear_doubt, str(item_id))


@app.get("/items/{item_id}/measures")
async def read_measures(item_id: UUID) -> intake.Measures:
    return await _edit(lambda connection: intake.measures(connection, client(), str(item_id)))


@app.post("/items/{item_id}/duplicate", status_code=201)
async def duplicate_item(item_id: UUID) -> intake.Entry:
    return await _edit(intake.duplicate_item, str(item_id))


@app.get("/target")
async def read_target(day: date | None = None) -> summary.Target | None:
    return await _edit(summary.target_on, day or today())


@app.put("/target")
async def set_target(body: summary.TargetIn) -> summary.Target:
    return await _edit(summary.set_target, body)


@app.get("/settings")
async def read_settings() -> notices.Settings:
    return await _edit(notices.settings)


@app.put("/settings")
async def save_settings(body: notices.Settings) -> notices.Settings:
    return await _edit(notices.save, body)


class ReferencesOut(BaseModel):
    profile: summary.Profile
    references: list[summary.Reference]


@app.get("/references")
async def read_references() -> ReferencesOut:
    async def both(connection: AsyncConnection) -> ReferencesOut:
        person = await summary.profile(connection)
        found = await summary.references(connection, person)
        return ReferencesOut(profile=person, references=list(found.values()))

    return await _edit(both)


@app.get("/day/{day}/contributors/{nutrient}")
async def read_contributors(day: date, nutrient: str) -> detail.Contributors:

    async def ranked(connection: AsyncConnection) -> detail.Contributors:
        found = await intake.entries(connection, day, day)
        try:
            return detail.contributors(found, nutrient)
        except ValueError as error:
            raise NotFound(str(error)) from error

    return await _edit(ranked)


@app.get("/goals")
async def read_goals(day: date | None = None) -> dict:
    return await _edit(goals.current, day)


class GoalBody(BaseModel):
    min: float | None = None
    max: float | None = None
    unit: goals.Basis = "amount"
    profile: goals.Profile = "any"
    valid_from: date | None = None


@app.put("/goals/{nutrient}")
async def set_goal(nutrient: str, body: GoalBody) -> dict:
    try:
        asked = goals.GoalIn(nutrient=nutrient, **body.model_dump())
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return await _edit(goals.set_goal, asked)


@app.delete("/goals/{nutrient}")
async def reset_goal(nutrient: str, profile: goals.Profile = "any") -> dict:
    try:
        asked = goals.GoalIn(nutrient=nutrient, profile=profile, reset=True)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return await _edit(goals.set_goal, asked)


class CompleteBody(BaseModel):
    complete: bool = True


@app.put("/day-complete/{day}")
async def set_day_complete(day: date, body: CompleteBody) -> dict:

    async def marked(connection: AsyncConnection) -> dict:
        done = await expenditure.mark(connection, day, body.complete, today())
        return {"day": day.isoformat(), "complete": done}

    return await _edit(marked)


class DayKindBody(BaseModel):
    kind: goals.Kind | None = None


@app.put("/day-kind/{day}")
async def set_day_kind(day: date, body: DayKindBody) -> goals.DayKind:
    return await _edit(goals.set_day_kind, day, body.kind)


@app.put("/references/{nutrient}", status_code=204)
async def set_reference(nutrient: str, body: summary.ReferenceIn) -> Response:
    await _edit(summary.set_reference, nutrient, body)
    return Response(status_code=204)


@app.delete("/references/{nutrient}", status_code=204)
async def reset_reference(nutrient: str) -> Response:
    await _edit(summary.set_reference, nutrient, None)
    return Response(status_code=204)


@app.get("/nutrients")
async def read_nutrients() -> list[dict]:
    return [
        {
            "key": one.key,
            "name": one.name,
            "unit": one.unit,
            "group": one.group,
            "front": one.front,
            "digits": one.digits,
        }
        for one in arga_nutrients.NUTRIENTS
    ]


SERVICES = {contracts.INTAKE_REPLACE_FOOD: contracts.IntakeReplaceFood}


@app.post("/capabilities/{capability}")
async def capability(
    capability: str,
    request: Request,
    x_module_token: str = Header(default=""),
    x_arga_module: str = Header(default=""),
) -> dict:
    expected = os.environ.get("MODULE_REGISTRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Macros no tiene MODULE_REGISTRATION_TOKEN")
    if not hmac.compare_digest(x_module_token, expected):
        raise HTTPException(status_code=401, detail="solo el kernel pide cosas a Macros")
    shape = SERVICES.get(capability)
    if shape is None:
        raise HTTPException(status_code=404, detail=f"Macros no sabe hacer '{capability}'")
    require_person()
    try:
        asked = shape.model_validate(await request.json())
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    answer = await _edit(intake.replace_food, client(), asked)
    print(f"sustituido  {asked.old_id} → {asked.new_id} para {x_arga_module}", flush=True)
    return answer


service.serve_ui()
