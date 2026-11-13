from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_contracts as contracts
import arga_nutrients
from macros import catalog, meals, metrics, pantry
from macros.common import Conflict, NotFound, enqueue, is_uuid, local_day, now, timezone, zone

Kind = Literal["food", "recipe", "quick", "water"]
Unit = Literal["g", "ml", "unit", "serving", "kcal"]
MAX_ITEMS = 20


class QuickMacros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protein: float | None = Field(default=None, ge=0, le=500)
    carbs: float | None = Field(default=None, ge=0, le=1000)
    fat: float | None = Field(default=None, ge=0, le=500)


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind = "food"
    food_id: str | None = None
    source: Literal["usda", "off"] | None = None
    source_ref: str | None = Field(default=None, max_length=40)
    recipe_id: str | None = None
    name: str | None = Field(default=None, max_length=200)
    quantity: float = Field(gt=0, le=100_000)
    unit: Unit = "g"
    estimated: bool = False
    quick: QuickMacros | None = None
    portion: str | None = Field(default=None, min_length=1, max_length=40)
    as_purchased: bool = False
    unsure: bool = False
    dish: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def _coherent(self) -> ItemIn:
        if self.kind == "food":
            if not self.food_id and not (self.source and self.source_ref):
                raise ValueError("a food needs food_id, or source and source_ref")
            if self.unit not in ("g", "ml", "unit"):
                raise ValueError("a food goes in g, ml or unit")
            if self.portion is not None and self.unit != "unit":
                raise ValueError("a portion counts units: it goes with unit")
        elif self.portion is not None or self.as_purchased:
            raise ValueError("portion and as_purchased belong to a food")
        if self.kind == "recipe":
            if not self.recipe_id:
                raise ValueError("a recipe needs recipe_id")
            if self.unit not in ("serving", "g"):
                raise ValueError("a recipe goes in serving or g")
        elif self.kind == "quick":
            if self.unit != "kcal":
                raise ValueError("a quick estimate goes in kcal")
            if not (self.name or "").strip():
                raise ValueError("a quick estimate needs name: what it was")
        elif self.kind == "water" and self.unit != "ml":
            raise ValueError("water goes in ml")
        return self


class EntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eaten_at: datetime | None = None
    meal: meals.Meal | None = None
    said: str | None = Field(default=None, max_length=1000)
    items: list[ItemIn] = Field(min_length=1, max_length=MAX_ITEMS)
    planned: bool = False


class ItemChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    quantity: float = Field(gt=0, le=100_000)
    unit: Unit | None = None
    estimated: bool | None = None


class ItemSwap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    food_id: str | None = None
    source: Literal["usda", "off"] | None = None
    source_ref: str | None = Field(default=None, max_length=40)
    recipe_id: str | None = None

    @model_validator(mode="after")
    def _one(self) -> ItemSwap:
        given = [bool(self.food_id), bool(self.source and self.source_ref), bool(self.recipe_id)]
        if sum(given) != 1:
            raise ValueError("exactly one of food_id, source with source_ref, or recipe_id")
        return self


class EntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eaten_at: datetime | None = None
    meal: meals.Meal | None = None
    change: list[ItemChange] = Field(default_factory=list, max_length=MAX_ITEMS)
    add: list[ItemIn] = Field(default_factory=list, max_length=MAX_ITEMS)
    remove: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    swap: list[ItemSwap] = Field(default_factory=list, max_length=MAX_ITEMS)


class Item(BaseModel):
    id: str
    position: int
    kind: Kind
    name: str
    quantity: float
    unit: Unit
    grams: float | None
    estimated: bool
    food_id: str | None
    recipe_id: str | None
    nutrients: dict[str, float]
    portion: str | None = None
    doubt: str | None = None
    dish: str | None = None


class Entry(BaseModel):
    id: str
    eaten_at: datetime
    day: date
    said: str | None
    origin: str
    items: list[Item]
    nutrients: dict[str, float]
    status: str = "confirmed"
    meal: meals.Meal = "breakfast"


@dataclass
class Line:
    kind: str
    name: str
    quantity: float
    unit: str
    grams: float | None
    estimated: bool
    food_id: str | None = None
    recipe_id: str | None = None
    recipe_version_id: str | None = None
    basis: dict[str, float] | None = None
    basis_per: str | None = None
    nutrients: dict[str, float] | None = None
    portion: str | None = None
    doubt: str | None = None
    dish: str | None = None


def food_grams(
    quantity: float,
    unit: str,
    food: dict[str, Any],
    portion: str | None = None,
    as_purchased: bool = False,
) -> float:
    raw = _raw_grams(quantity, unit, food, portion)
    fraction = food.get("edible_fraction")
    return raw * float(fraction) if as_purchased and fraction else raw


def _raw_grams(quantity: float, unit: str, food: dict[str, Any], portion: str | None) -> float:
    if unit == "g":
        return quantity
    if unit == "ml":
        return quantity * float(food.get("density_g_ml") or 1.0)
    if portion is not None:
        portions = food.get("portions") or {}
        grams = portions.get(portion.strip().lower())
        if not grams:
            known = ", ".join(sorted(portions)) or "none"
            raise Conflict(
                f"{food['label']} has no portion '{portion}' (it has: {known}): "
                "say it in grams, or add it in Recipes"
            )
        return quantity * float(grams)
    per_unit = food.get("grams_per_unit")
    if not per_unit:
        raise Conflict(
            f"the weight of one unit of {food['label']} is unknown: say it in grams, "
            "or set its weight per unit in Recipes"
        )
    return quantity * float(per_unit)


def _unit_grams(item: ItemIn, food: dict[str, Any]) -> float | None:
    if item.unit != "unit" or item.portion is not None or item.as_purchased:
        unit = food.get("unit_name") or "unit"
        raise Conflict(f"{food['label']} is logged in units ({unit}): unit and the quantity")
    per_one = food.get("grams_per_unit")
    return None if not per_one else item.quantity * float(per_one)


def compute(line: Line) -> Line:
    if line.kind == "food" and line.basis_per == "unit":
        assert line.basis is not None
        line.nutrients = arga_nutrients.scaled(line.basis, line.quantity * 100)
    elif line.kind == "food":
        assert line.basis is not None
        line.nutrients = arga_nutrients.scaled(line.basis, line.grams or 0)
    elif line.kind == "recipe":
        assert line.basis is not None
        servings = line.quantity
        if line.unit == "g":
            per_serving = float(line.basis.get("_grams") or 0)
            if per_serving <= 0:
                raise Conflict(
                    f"{line.name} does not say what a serving weighs: say it in servings"
                )
            servings = line.quantity / per_serving
        line.nutrients = {
            key: round(value * servings, 4)
            for key, value in line.basis.items()
            if not key.startswith("_")
        }
    elif line.kind == "water":
        line.nutrients = {}
    return line


async def resolve(
    connection: AsyncConnection, client: httpx.AsyncClient, items: list[ItemIn]
) -> list[Line]:
    for item in items:
        if item.kind == "food" and not item.food_id:
            imported = await pantry.import_food(client, item.source or "", item.source_ref or "")
            item.food_id = imported["id"]
    wanted = [item.food_id for item in items if item.kind == "food" and is_uuid(item.food_id)]
    found = await pantry.foods(client, [one for one in wanted if one])
    recipes: dict[str, dict[str, Any]] = {}

    lines = []
    for item in items:
        if item.kind == "food":
            food = found.get(item.food_id or "")
            if food is None:
                raise NotFound(f"food {item.food_id} in the pantry")
            per_unit = food.get("nutrients_per") == "unit"
            grams = (
                _unit_grams(item, food)
                if per_unit
                else food_grams(item.quantity, item.unit, food, item.portion, item.as_purchased)
            )
            name = (item.name or food["label"]).strip()
            line = Line(
                kind="food",
                name=name[:200],
                quantity=item.quantity,
                unit=item.unit,
                grams=None if grams is None else round(grams, 2),
                estimated=item.estimated,
                food_id=food["id"],
                basis=arga_nutrients.only_known(food["nutrients"]),
                basis_per="unit" if per_unit else "100g",
                portion=None if item.portion is None else item.portion.strip().lower(),
            )
        elif item.kind == "recipe":
            if not is_uuid(item.recipe_id):
                raise NotFound(f"recipe {item.recipe_id}")
            recipe = recipes.get(item.recipe_id or "") or await pantry.recipe(
                client, item.recipe_id or ""
            )
            recipes[recipe["id"]] = recipe
            basis = arga_nutrients.only_known(recipe["per_serving"])
            basis["_grams"] = float(recipe.get("grams_per_serving") or 0)
            servings = (
                item.quantity if item.unit == "serving" else item.quantity / (basis["_grams"] or 1)
            )
            line = Line(
                kind="recipe",
                name=(item.name or recipe["name"]).strip(),
                quantity=item.quantity,
                unit=item.unit,
                grams=round(basis["_grams"] * servings, 2) if basis["_grams"] else None,
                estimated=item.estimated,
                recipe_id=recipe["id"],
                recipe_version_id=recipe["version_id"],
                basis=basis,
                basis_per="serving",
            )
        elif item.kind == "quick":
            said = {"kcal": item.quantity}
            if item.quick is not None:
                said.update({k: v for k, v in item.quick.model_dump().items() if v is not None})
            line = Line(
                kind="quick",
                name=(item.name or "").strip(),
                quantity=item.quantity,
                unit="kcal",
                grams=None,
                estimated=True,
                nutrients=said,
            )
        else:
            line = Line(
                kind="water",
                name=(item.name or "Agua").strip(),
                quantity=item.quantity,
                unit="ml",
                grams=item.quantity,
                estimated=item.estimated,
            )
        lines.append(compute(line))
    return lines


INSERT_ENTRY = text("""
    insert into macros.macros_entry (eaten_at, tz, day, said, origin, status)
    values (:eaten_at, :tz, :day, :said, :origin, :status)
    returning id
""")

INSERT_ITEM = text("""
    insert into macros.macros_item
        (entry_id, position, kind, food_id, recipe_id, recipe_version_id, name, quantity, unit,
         grams, estimated, basis, basis_per, nutrients, portion, doubt, dish)
    values (cast(:entry as uuid), :position, :kind, cast(:food_id as uuid),
            cast(:recipe_id as uuid), cast(:recipe_version_id as uuid), :name, :quantity, :unit,
            :grams, :estimated, cast(:basis as jsonb), :basis_per, cast(:nutrients as jsonb),
            :portion, :doubt, :dish)
""")

NEXT_POSITION = text("""
    select coalesce(max(position), 0) + 1 from macros.macros_item
    where entry_id = cast(:entry as uuid)
""")


def _moment(eaten_at: datetime | None) -> datetime:
    if eaten_at is None:
        return now()
    if eaten_at.tzinfo is None:
        return eaten_at.replace(tzinfo=zone())
    return eaten_at


async def _insert_items(connection: AsyncConnection, entry_id: str, lines: list[Line]) -> None:
    position = int(await connection.scalar(NEXT_POSITION, {"entry": entry_id}))
    for line in lines:
        await connection.execute(
            INSERT_ITEM,
            {
                "entry": entry_id,
                "position": position,
                "kind": line.kind,
                "food_id": line.food_id,
                "recipe_id": line.recipe_id,
                "recipe_version_id": line.recipe_version_id,
                "name": line.name[:200],
                "quantity": round(line.quantity, 2),
                "unit": line.unit,
                "grams": line.grams,
                "estimated": line.estimated,
                "basis": None if line.basis is None else json.dumps(line.basis),
                "basis_per": line.basis_per,
                "nutrients": json.dumps(line.nutrients or {}),
                "portion": line.portion,
                "doubt": line.doubt,
                "dish": (line.dish or "").strip() or None,
            },
        )
        position += 1


async def log(
    connection: AsyncConnection,
    client: httpx.AsyncClient,
    request: EntryIn,
    origin: Literal["claude", "app"] = "app",
) -> Entry:
    lines = await resolve(connection, client, request.items)
    for line, asked in zip(lines, request.items, strict=True):
        line.dish = asked.dish
    if origin == "claude":
        await doubts(connection, lines, request.items)
    status = "planned" if request.planned else "confirmed"
    eaten_at = request.eaten_at
    if request.meal is not None:
        eaten_at = await meals.moment_for(connection, request.meal, None, eaten_at)
    return await write(connection, lines, eaten_at, request.said, origin, status)


EVER_LOGGED = text("""
    select exists (
        select 1 from macros.macros_item
        where food_id = cast(:food as uuid) or recipe_id = cast(:recipe as uuid)
    )
""")


async def doubts(connection: AsyncConnection, lines: list[Line], items: list[ItemIn]) -> None:
    for line, asked in zip(lines, items, strict=True):
        if line.kind not in ("food", "recipe"):
            continue
        if asked.unsure:
            line.doubt = "unsure"
            continue
        seen = await connection.scalar(
            EVER_LOGGED, {"food": line.food_id, "recipe": line.recipe_id}
        )
        if not seen:
            line.doubt = "first"


async def write(
    connection: AsyncConnection,
    lines: list[Line],
    eaten_at: datetime | None,
    said: str | None,
    origin: str,
    status: str = "confirmed",
) -> Entry:
    moment = _moment(eaten_at)
    day = local_day(moment)
    entry_id = str(
        await connection.scalar(
            INSERT_ENTRY,
            {
                "eaten_at": moment,
                "tz": timezone(),
                "day": day,
                "said": (said or "").strip() or None,
                "origin": origin,
                "status": status,
            },
        )
    )
    await _insert_items(connection, entry_id, lines)
    return await _changed(connection, entry_id, {day})


ITEM_ROW = text("""
    select i.id, i.entry_id, i.kind, i.name, i.quantity, i.unit, i.grams, i.estimated,
           i.basis, i.basis_per, i.food_id, i.recipe_id, i.recipe_version_id, i.nutrients
    from macros.macros_item i
    where i.id = cast(:id as uuid)
""")

UPDATE_ITEM = text("""
    update macros.macros_item
       set quantity = :quantity, unit = :unit, grams = :grams, estimated = :estimated,
           nutrients = cast(:nutrients as jsonb),
           portion = case when :unit = 'unit' then portion end
     where id = cast(:id as uuid)
""")

MOVE_ENTRY = text("""
    update macros.macros_entry set eaten_at = :eaten_at, day = :day
     where id = cast(:id as uuid)
""")

DELETE_ITEM = text("delete from macros.macros_item where id = cast(:id as uuid)")
DELETE_ENTRY = text("delete from macros.macros_entry where id = cast(:id as uuid) returning day")
ITEMS_LEFT = text("select count(*) from macros.macros_item where entry_id = cast(:id as uuid)")


async def _row(connection: AsyncConnection, item_id: str) -> Any:
    row = (
        (await connection.execute(ITEM_ROW, {"id": item_id})).first() if is_uuid(item_id) else None
    )
    if row is None:
        raise NotFound(f"line {item_id}")
    return row


def _requantified(row: Any, quantity: float, unit: str, estimated: bool) -> Line:
    line = Line(
        kind=row.kind,
        name=row.name,
        quantity=quantity,
        unit=unit,
        grams=None,
        estimated=estimated,
        basis=row.basis,
        basis_per=row.basis_per,
    )
    if row.kind == "food" and row.basis_per == "unit":
        if unit != "unit":
            raise Conflict(f"{row.name} is logged in units")
        if row.grams is not None and float(row.quantity) > 0:
            line.grams = round(float(row.grams) / float(row.quantity) * quantity, 2)
    elif row.kind == "food":
        if unit == row.unit and row.grams is not None and float(row.quantity) > 0:
            line.grams = round(float(row.grams) / float(row.quantity) * quantity, 2)
        elif unit in ("g", "ml"):
            line.grams = quantity
        else:
            raise Conflict(f"{row.name}: change it in grams")
    elif row.kind == "recipe":
        if unit not in ("serving", "g"):
            raise Conflict("a recipe goes in servings or grams")
        grams = float((row.basis or {}).get("_grams") or 0)
        servings = quantity if unit == "serving" else quantity / (grams or 1)
        line.grams = round(grams * servings, 2) if grams else None
    elif row.kind == "quick":
        if unit != "kcal":
            raise Conflict("a quick estimate goes in kcal")
        previous = float(row.quantity)
        return Line(
            kind="quick",
            name=row.name,
            quantity=quantity,
            unit="kcal",
            grams=None,
            estimated=True,
            nutrients={
                key: round(value * quantity / previous, 3)
                for key, value in (row.nutrients or {}).items()
            }
            or {"kcal": quantity},
        )
    else:
        if unit != "ml":
            raise Conflict("water goes in ml")
        line.grams = quantity
    return compute(line)


async def update(
    connection: AsyncConnection, client: httpx.AsyncClient, entry_id: str, patch: EntryPatch
) -> Entry:
    entry = await _entry_row(connection, entry_id)
    days = {entry.day}
    wanted = patch.eaten_at
    if patch.meal is not None:
        wanted = await meals.moment_for(connection, patch.meal, entry.day, patch.eaten_at)
    if wanted is not None:
        moment = _moment(wanted)
        day = local_day(moment)
        await connection.execute(MOVE_ENTRY, {"id": entry_id, "eaten_at": moment, "day": day})
        days.add(day)
    for change in patch.change:
        row = await _row(connection, change.item_id)
        if str(row.entry_id) != entry_id:
            raise NotFound(f"line {change.item_id} in that entry")
        line = _requantified(
            row,
            change.quantity,
            change.unit or row.unit,
            row.estimated if change.estimated is None else change.estimated,
        )
        await connection.execute(
            UPDATE_ITEM,
            {
                "id": change.item_id,
                "quantity": round(line.quantity, 2),
                "unit": line.unit,
                "grams": line.grams,
                "estimated": line.estimated,
                "nutrients": json.dumps(line.nutrients or {}),
            },
        )
    for swap in patch.swap:
        row = await _row(connection, swap.item_id)
        if str(row.entry_id) != entry_id:
            raise NotFound(f"line {swap.item_id} in that entry")
        await _swap(connection, client, entry_id, row, swap)
    for item_id in patch.remove:
        row = await _row(connection, item_id)
        if str(row.entry_id) != entry_id:
            raise NotFound(f"line {item_id} in that entry")
        await connection.execute(DELETE_ITEM, {"id": item_id})
    if patch.add:
        lines = await resolve(connection, client, patch.add)
        for line, asked in zip(lines, patch.add, strict=True):
            line.dish = asked.dish
        await _insert_items(connection, entry_id, lines)
    if not await connection.scalar(ITEMS_LEFT, {"id": entry_id}):
        raise Conflict("an entry without lines is nothing: delete the whole entry")
    return await _changed(connection, entry_id, days)


def _kept(row: Any, swap: ItemSwap) -> ItemIn:
    grams = None if row.grams is None else float(row.grams)
    if swap.recipe_id:
        if row.kind == "recipe" and row.unit == "serving":
            quantity, unit = float(row.quantity), "serving"
        elif grams:
            quantity, unit = grams, "g"
        else:
            raise Conflict(f"what {row.name} weighed is unknown: say it in servings")
        return ItemIn(
            kind="recipe",
            recipe_id=swap.recipe_id,
            quantity=quantity,
            unit=unit,
            estimated=row.estimated,
        )
    if row.kind == "food" and row.basis_per == "unit":
        quantity, unit = float(row.quantity), "unit"
    elif grams:
        quantity, unit = grams, "g"
    else:
        raise Conflict(f"what {row.name} weighed is unknown: say it in grams")
    return ItemIn(
        kind="food",
        food_id=swap.food_id,
        source=swap.source,
        source_ref=swap.source_ref,
        quantity=quantity,
        unit=unit,
        estimated=row.estimated,
    )


SWAPPED = text("""
    update macros.macros_item
       set kind = :kind, food_id = cast(:food_id as uuid), recipe_id = cast(:recipe_id as uuid),
           recipe_version_id = cast(:recipe_version_id as uuid), name = :name,
           quantity = :quantity, unit = :unit, grams = :grams, estimated = :estimated,
           basis = cast(:basis as jsonb), basis_per = :basis_per,
           nutrients = cast(:nutrients as jsonb), portion = null, doubt = null
     where id = cast(:id as uuid)
""")


async def _swap(
    connection: AsyncConnection,
    client: httpx.AsyncClient,
    entry_id: str,
    row: Any,
    swap: ItemSwap,
) -> None:
    if row.kind not in ("food", "recipe"):
        raise Conflict("only a food or a recipe can be swapped")
    [line] = await resolve(connection, client, [_kept(row, swap)])
    await connection.execute(
        SWAPPED,
        {
            "id": str(row.id),
            "kind": line.kind,
            "food_id": line.food_id,
            "recipe_id": line.recipe_id,
            "recipe_version_id": line.recipe_version_id,
            "name": line.name[:200],
            "quantity": round(line.quantity, 2),
            "unit": line.unit,
            "grams": line.grams,
            "estimated": line.estimated,
            "basis": None if line.basis is None else json.dumps(line.basis),
            "basis_per": line.basis_per,
            "nutrients": json.dumps(line.nutrients or {}),
        },
    )


class Measure(BaseModel):
    name: str
    grams: float


class Measures(BaseModel):
    item_id: str
    measures: list[Measure]


async def measures(
    connection: AsyncConnection, client: httpx.AsyncClient, item_id: str
) -> Measures:
    row = await _row(connection, item_id)
    found: list[Measure] = []
    if row.kind == "food" and row.food_id is not None and row.basis_per != "unit":
        food = (await pantry.foods(client, [str(row.food_id)])).get(str(row.food_id)) or {}
        for name, grams in sorted((food.get("portions") or {}).items(), key=lambda one: one[1]):
            if grams:
                found.append(Measure(name=name, grams=float(grams)))
        per_unit = food.get("grams_per_unit")
        if per_unit and not any(one.grams == float(per_unit) for one in found):
            found.append(Measure(name=catalog.t("measure.unit"), grams=float(per_unit)))
    elif row.kind == "recipe":
        grams = float((row.basis or {}).get("_grams") or 0)
        if grams:
            found.append(Measure(name=catalog.t("measure.serving"), grams=grams))
    return Measures(item_id=str(row.id), measures=found)


CLEAR_DOUBT = text("""
    update macros.macros_item set doubt = null where id = cast(:id as uuid) returning entry_id
""")


async def clear_doubt(connection: AsyncConnection, item_id: str) -> Entry:
    if not is_uuid(item_id):
        raise NotFound(f"line {item_id}")
    entry_id = await connection.scalar(CLEAR_DOUBT, {"id": item_id})
    if entry_id is None:
        raise NotFound(f"line {item_id}")
    return await one(connection, str(entry_id))


ITEMS_OF_FOOD = text("""
    select i.id, i.entry_id, i.name, i.quantity, i.unit, i.grams, i.basis_per, e.day
    from macros.macros_item i
    join macros.macros_entry e on e.id = i.entry_id
    where i.kind = 'food' and i.food_id = cast(:food as uuid)
""")

SWAP_ITEM = text("""
    update macros.macros_item
       set food_id = cast(:food as uuid), name = :name, grams = :grams,
           basis = cast(:basis as jsonb), nutrients = cast(:nutrients as jsonb)
     where id = cast(:id as uuid)
""")


def _renamed(name: str, old_label: str, new_label: str) -> str:
    if name == old_label:
        return new_label[:200]
    if name.startswith(f"{old_label} ("):
        return (new_label + name[len(old_label) :])[:200]
    return name


async def replace_food(
    connection: AsyncConnection, client: httpx.AsyncClient, asked: contracts.IntakeReplaceFood
) -> dict[str, Any]:
    rows = (await connection.execute(ITEMS_OF_FOOD, {"food": asked.old_id})).all()
    if not rows:
        return contracts.intake_replaced(items=0, entries=0, days=[])
    found = await pantry.foods(client, [asked.new_id])
    food = found.get(asked.new_id)
    if food is None:
        raise NotFound(f"food {asked.new_id} in the pantry")
    per_unit = food.get("nutrients_per") == "unit"
    basis = arga_nutrients.only_known(food["nutrients"])
    entries: dict[str, set[date]] = {}
    for row in rows:
        if (row.basis_per == "unit") != per_unit:
            raise Conflict(f"{row.name}: one is per 100 g and the other per unit")
        line = compute(
            Line(
                kind="food",
                name=row.name,
                quantity=float(row.quantity),
                unit=row.unit,
                grams=None if row.grams is None else float(row.grams),
                estimated=False,
                basis=basis,
                basis_per=row.basis_per,
            )
        )
        await connection.execute(
            SWAP_ITEM,
            {
                "id": str(row.id),
                "food": asked.new_id,
                "name": _renamed(row.name, asked.old_label, asked.new_label),
                "grams": line.grams,
                "basis": json.dumps(basis),
                "nutrients": json.dumps(line.nutrients or {}),
            },
        )
        entries.setdefault(str(row.entry_id), set()).add(row.day)
    for entry_id, days in entries.items():
        await _changed(connection, entry_id, days)
    every = sorted({day for days in entries.values() for day in days})
    return contracts.intake_replaced(
        items=len(rows), entries=len(entries), days=[one.isoformat() for one in every]
    )


CONFIRM = text("""
    update macros.macros_entry set status = 'confirmed', eaten_at = :eaten_at, day = :day
     where id = cast(:id as uuid)
""")


async def confirm(
    connection: AsyncConnection, entry_id: str, eaten_at: datetime | None = None
) -> Entry:
    row = await _entry_row(connection, entry_id)
    if row.status != "planned":
        raise Conflict("esa entrada ya estaba confirmada")
    moment = row.eaten_at if eaten_at is None else _moment(eaten_at)
    day = local_day(moment)
    await connection.execute(CONFIRM, {"id": entry_id, "eaten_at": moment, "day": day})
    return await _changed(connection, entry_id, {row.day, day})


UNCONFIRM = text("""
    update macros.macros_entry set status = 'planned' where id = cast(:id as uuid)
""")


async def unconfirm(connection: AsyncConnection, entry_id: str) -> Entry:
    row = await _entry_row(connection, entry_id)
    if row.status != "confirmed":
        raise Conflict("esa entrada no estaba confirmada")
    await connection.execute(UNCONFIRM, {"id": entry_id})
    await enqueue(connection, "intake", {"entry_id": entry_id, "day": row.day, "removed": True})
    await metrics.refresh(connection, {row.day})
    return await one(connection, entry_id)


RENAME_DISH = text("""
    update macros.macros_item set dish = :to
     where entry_id = cast(:entry as uuid) and dish = :from
    returning id
""")


async def rename_dish(
    connection: AsyncConnection, entry_id: str, old: str, new: str | None
) -> Entry:
    await _entry_row(connection, entry_id)
    changed = (
        await connection.execute(
            RENAME_DISH, {"entry": entry_id, "from": old, "to": (new or "").strip() or None}
        )
    ).all()
    if not changed:
        raise NotFound(f"dish '{old}' in that entry")
    return await _changed(connection, entry_id, set())


async def planned(connection: AsyncConnection, day: date) -> list[Entry]:
    return await entries(connection, day, day, None, ("planned",))


async def delete_entry(connection: AsyncConnection, entry_id: str) -> None:
    row = await _entry_row(connection, entry_id)
    day = await connection.scalar(DELETE_ENTRY, {"id": entry_id})
    if row.status == "planned":
        return
    await enqueue(connection, "intake", {"entry_id": entry_id, "day": day, "removed": True})
    await metrics.refresh(connection, {day})


async def delete_item(connection: AsyncConnection, item_id: str) -> Entry | None:
    row = await _row(connection, item_id)
    entry_id = str(row.entry_id)
    if await connection.scalar(ITEMS_LEFT, {"id": entry_id}) <= 1:
        await delete_entry(connection, entry_id)
        return None
    entry = await _entry_row(connection, entry_id)
    await connection.execute(DELETE_ITEM, {"id": item_id})
    return await _changed(connection, entry_id, {entry.day})


async def duplicate_item(connection: AsyncConnection, item_id: str) -> Entry:
    row = await _row(connection, item_id)
    entry_id = str(row.entry_id)
    await connection.execute(
        text("""
            insert into macros.macros_item
                (entry_id, position, kind, food_id, recipe_id, recipe_version_id, name, quantity,
                 unit, grams, estimated, basis, basis_per, nutrients, portion, dish)
            select entry_id, (select max(position) + 1 from macros.macros_item
                               where entry_id = i.entry_id),
                   kind, food_id, recipe_id, recipe_version_id, name, quantity, unit, grams,
                   estimated, basis, basis_per, nutrients, portion, dish
            from macros.macros_item i where id = cast(:id as uuid)
        """),
        {"id": item_id},
    )
    entry = await _entry_row(connection, entry_id)
    return await _changed(connection, entry_id, {entry.day})


async def repeat(
    connection: AsyncConnection, entry_id: str, eaten_at: datetime | None = None
) -> Entry:
    await _entry_row(connection, entry_id)
    moment = _moment(eaten_at)
    day = local_day(moment)
    new_id = str(
        await connection.scalar(
            INSERT_ENTRY,
            {
                "eaten_at": moment,
                "tz": timezone(),
                "day": day,
                "said": None,
                "origin": "app",
                "status": "confirmed",
            },
        )
    )
    await connection.execute(
        text("""
            insert into macros.macros_item
                (entry_id, position, kind, food_id, recipe_id, recipe_version_id, name, quantity,
                 unit, grams, estimated, basis, basis_per, nutrients, portion, dish)
            select cast(:new as uuid), position, kind, food_id, recipe_id, recipe_version_id,
                   name, quantity, unit, grams, estimated, basis, basis_per, nutrients, portion,
                   dish
            from macros.macros_item where entry_id = cast(:old as uuid)
        """),
        {"new": new_id, "old": entry_id},
    )
    return await _changed(connection, new_id, {day})


COPY_ITEMS = text("""
    insert into macros.macros_item
        (entry_id, position, kind, food_id, recipe_id, recipe_version_id, name, quantity, unit,
         grams, estimated, basis, basis_per, nutrients, portion, dish)
    select cast(:new as uuid),
           row_number() over (order by e.eaten_at, i.position)
               + (select coalesce(max(position), 0) from macros.macros_item
                   where entry_id = cast(:new as uuid)),
           i.kind, i.food_id, i.recipe_id, i.recipe_version_id, i.name, i.quantity, i.unit,
           i.grams, i.estimated, i.basis, i.basis_per, i.nutrients, i.portion, i.dish
    from macros.macros_item i join macros.macros_entry e on e.id = i.entry_id
    where i.id = any(cast(:items as uuid[]))
""")

ITEMS_OF_ENTRIES = text("""
    select i.id from macros.macros_item i join macros.macros_entry e on e.id = i.entry_id
    where i.entry_id = any(cast(:entries as uuid[]))
    order by e.eaten_at, i.position
""")


async def copy_items(
    connection: AsyncConnection,
    item_ids: list[str],
    moment: datetime,
    origin: str = "app",
    said: str | None = None,
    status: str = "confirmed",
) -> Entry:
    wanted = [one for one in dict.fromkeys(item_ids) if is_uuid(one)]
    if not wanted or len(wanted) != len(set(item_ids)):
        raise NotFound("one of those lines")
    found = (
        await connection.execute(
            text("select count(*) from macros.macros_item where id = any(cast(:ids as uuid[]))"),
            {"ids": wanted},
        )
    ).scalar_one()
    if found != len(wanted):
        raise NotFound("one of those lines")
    day = local_day(moment)
    new_id = str(
        await connection.scalar(
            INSERT_ENTRY,
            {
                "eaten_at": moment,
                "tz": timezone(),
                "day": day,
                "said": said,
                "origin": origin,
                "status": status,
            },
        )
    )
    await connection.execute(COPY_ITEMS, {"new": new_id, "items": wanted})
    return await _changed(connection, new_id, {day})


SOURCE_MEAL = text("""
    select e.eaten_at, e.tz
    from macros.macros_item i join macros.macros_entry e on e.id = i.entry_id
    where i.id = cast(:id as uuid)
""")


async def repeat_items(
    connection: AsyncConnection,
    item_ids: list[str],
    meal: meals.Meal | None = None,
    day: date | None = None,
    eaten_at: datetime | None = None,
    origin: str = "app",
) -> Entry:
    if not item_ids:
        raise NotFound("any line to repeat")
    if meal is None and eaten_at is None:
        source = (
            (await connection.execute(SOURCE_MEAL, {"id": item_ids[0]})).first()
            if is_uuid(item_ids[0])
            else None
        )
        if source is None:
            raise NotFound(f"line {item_ids[0]}")
        meal = meals.meal_of(source.eaten_at, source.tz or timezone())
    if meal is not None:
        moment = await meals.moment_for(connection, meal, day, eaten_at)
    else:
        moment = _moment(eaten_at)
    return await copy_items(connection, item_ids, moment, origin)


async def items_of_entries(connection: AsyncConnection, entry_ids: list[str]) -> list[str]:
    wanted = [one for one in entry_ids if is_uuid(one)]
    found = (await connection.execute(ITEMS_OF_ENTRIES, {"entries": wanted})).scalars().all()
    if not found:
        raise NotFound("esas entradas")
    return [str(one) for one in found]


async def in_meal(
    connection: AsyncConnection, day: date, meal: str, statuses: tuple[str, ...] = ("confirmed",)
) -> list[Entry]:
    return [one for one in await entries(connection, day, day, None, statuses) if one.meal == meal]


async def repeat_meal(
    connection: AsyncConnection,
    from_day: date,
    meal: meals.Meal,
    day: date | None = None,
    to_meal: meals.Meal | None = None,
    origin: str = "app",
) -> Entry:
    found = await in_meal(connection, from_day, meal)
    if not found:
        raise NotFound(f"anything logged at {meal} on {from_day.isoformat()}")
    target = to_meal or meal
    moment = await meals.moment_for(connection, target, day)
    items = [item.id for entry in found for item in entry.items]
    return await copy_items(connection, items, moment, origin)


async def move_meal(
    connection: AsyncConnection, day: date, meal: meals.Meal, at: time
) -> list[Entry]:
    found = await in_meal(connection, day, meal, ("confirmed", "planned"))
    if not found:
        raise NotFound(f"anything at {meal} that day")
    moment = datetime.combine(day, at, zone())
    moved = []
    for entry in found:
        await connection.execute(MOVE_ENTRY, {"id": entry.id, "eaten_at": moment, "day": day})
        moved.append(await _changed(connection, entry.id, {entry.day}))
    return moved


async def delete_meal(connection: AsyncConnection, day: date, meal: meals.Meal) -> int:
    found = await in_meal(connection, day, meal, ("confirmed", "planned"))
    for entry in found:
        await delete_entry(connection, entry.id)
    return len(found)


async def move_item(connection: AsyncConnection, item_id: str, meal: meals.Meal) -> Entry:
    row = await _row(connection, item_id)
    entry = await _entry_row(connection, str(row.entry_id))
    if await connection.scalar(ITEMS_LEFT, {"id": str(row.entry_id)}) <= 1:
        return await update(connection, None, str(row.entry_id), EntryPatch(meal=meal))  # type: ignore[arg-type]
    moment = await meals.moment_for(connection, meal, entry.day)
    moved = await copy_items(connection, [item_id], moment, entry.origin, None, entry.status)
    await connection.execute(DELETE_ITEM, {"id": item_id})
    await _changed(connection, str(row.entry_id), {entry.day})
    return moved


ENTRY_ROW = text("""
    select id, eaten_at, day, said, origin, status from macros.macros_entry
     where id = cast(:id as uuid)
""")

ENTRIES = text("""
    select e.id, e.eaten_at, e.tz, e.day, e.said, e.origin, e.status,
           i.id as item_id, i.position, i.kind, i.name, i.quantity, i.unit, i.grams,
           i.estimated, i.food_id, i.recipe_id, i.nutrients, i.portion, i.doubt, i.dish
    from macros.macros_entry e
    join macros.macros_item i on i.entry_id = e.id
    where e.day between :first and :last
      and (cast(:entry as uuid) is null or e.id = cast(:entry as uuid))
      and e.status = any(cast(:statuses as text[]))
    order by e.eaten_at, e.id, i.position
""")


async def _entry_row(connection: AsyncConnection, entry_id: str) -> Any:
    row = (
        (await connection.execute(ENTRY_ROW, {"id": entry_id})).first()
        if is_uuid(entry_id)
        else None
    )
    if row is None:
        raise NotFound(f"entry {entry_id}")
    return row


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


async def entries(
    connection: AsyncConnection,
    first: date,
    last: date,
    entry_id: str | None = None,
    statuses: tuple[str, ...] = ("confirmed",),
) -> list[Entry]:
    rows = (
        await connection.execute(
            ENTRIES,
            {"first": first, "last": last, "entry": entry_id, "statuses": list(statuses)},
        )
    ).all()
    found: dict[str, Entry] = {}
    for row in rows:
        key = str(row.id)
        if key not in found:
            found[key] = Entry(
                id=key,
                eaten_at=row.eaten_at,
                day=row.day,
                said=row.said,
                origin=row.origin,
                items=[],
                nutrients={},
                status=row.status,
                meal=meals.meal_of(row.eaten_at, row.tz or timezone()),
            )
        found[key].items.append(
            Item(
                id=str(row.item_id),
                position=row.position,
                kind=row.kind,
                name=row.name,
                quantity=float(row.quantity),
                unit=row.unit,
                grams=_number(row.grams),
                estimated=row.estimated,
                food_id=None if row.food_id is None else str(row.food_id),
                recipe_id=None if row.recipe_id is None else str(row.recipe_id),
                nutrients=arga_nutrients.only_known(row.nutrients),
                portion=row.portion,
                doubt=row.doubt,
                dish=row.dish,
            )
        )
    for entry in found.values():
        entry.nutrients = arga_nutrients.added(*(item.nutrients for item in entry.items))
    return list(found.values())


async def one(connection: AsyncConnection, entry_id: str) -> Entry:
    row = await _entry_row(connection, entry_id)
    [entry] = await entries(connection, row.day, row.day, entry_id, ("confirmed", "planned"))
    return entry


async def _changed(connection: AsyncConnection, entry_id: str, days: set[date]) -> Entry:
    entry = await one(connection, entry_id)
    if entry.status == "planned":
        return entry
    await enqueue(connection, "intake", intake_payload(entry))
    await metrics.refresh(connection, days | {entry.day})
    return entry


changed = _changed


def intake_payload(entry: Entry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "eaten_at": entry.eaten_at.isoformat(),
        "day": entry.day.isoformat(),
        "said": entry.said,
        "items": [
            {
                "name": item.name,
                "kind": item.kind,
                "quantity": item.quantity,
                "unit": item.unit,
                "portion": item.portion,
                "estimated": item.estimated,
                "kcal": item.nutrients.get("kcal"),
                "protein": item.nutrients.get("protein"),
            }
            for item in entry.items
        ],
        "removed": False,
    }
