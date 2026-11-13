from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import arga_nutrients
from recipes import hub, nutrition, sources
from recipes.recipes import Conflict, NotFound

UNITS = ("g", "ml", "unit", "tbsp", "tsp", "pinch")

ALIAS_HELP = (
    "What it is called at home, short and in the person's language: `chicken breast`, `onion`. "
    "It is what the recipe shows and what people type; the source's name stays beside it. One "
    "per food, and it cannot repeat on another. Empty or null, no alias."
)


class Macros(BaseModel):
    kcal: float = Field(ge=0, le=1000)
    protein: float = Field(ge=0, le=100)
    fat: float = Field(ge=0, le=100)
    carbs: float = Field(ge=0, le=100)
    fiber: float | None = Field(default=None, ge=0, le=100)
    salt: float | None = Field(default=None, ge=0, le=100)


class MacrosIn(Macros):
    pass


NUTRIENTS_HELP = (
    "Everything it has per 100 g besides the macros, with the keys of `list_nutrients`: "
    '`{"vitamin_d": 5, "caffeine": 80}`. The number is in the key\'s unit (µg, mg, g); if the '
    'label gives it in another, with its own: `{"omega3_epa": {"amount": 250, "unit": "mg"}}`. '
    "A key or unit that does not fit is rejected with its reason. What you do not know, leave "
    "out: what is missing does not count as zero."
)
PROVENANCE_HELP = (
    "Where these figures come from, briefly: \"HSN label\", \"estimated by the model\", "
    "\"home recipe\". It shows on the food's card: say it honestly, because a measured figure "
    "and an estimated one are not worth the same."
)
PORTIONS_HELP = (
    "The household measures, with the **edible** grams of each: "
    '`[{"name": "slice", "grams": 15}, {"name": "handful", "grams": 30}]`. Then a recipe or a '
    'log says "2 slices" in `unit` with `portion: "slice"`.'
)
EDIBLE_HELP = (
    "The share eaten of what is weighed whole, from 0 to 1: a 730 g tuna steak with bone and "
    "skin is ~600 g clean, 0.82. It applies to a quantity marked `as_purchased`. Without a "
    "value, all of it is eaten."
)
PER_UNIT_HELP = (
    "For a supplement taken in units: the unit's name, \"capsule\", \"tablet\", \"scoop\", "
    "\"drop\". Then `macros` and `nutrients` are what **one** unit has, as the label gives "
    "it, not per 100 g; and it is counted only in units. `grams_per_unit`, if known, is what "
    "one weighs. Without this, everything is per 100 g."
)
MICROS_FROM_HELP = (
    "Another food in your pantry (`food_id`) to take the micros this one lacks from: an Open "
    "Food Facts product with its label macros and the micros of the generic USDA entry. What "
    "this one has wins; macros are never borrowed."
)


class Portion(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    grams: float = Field(gt=0, le=5000)


def _typed(values: dict[str, Any]) -> dict[str, float]:
    try:
        return arga_nutrients.typed(values)
    except arga_nutrients.Invalid as error:
        raise ValueError(str(error)) from error


def _distinct(portions: list[Portion]) -> list[Portion]:
    names = [one.name.strip().lower() for one in portions]
    if len(names) != len(set(names)):
        raise ValueError("two portions with the same name")
    return portions


class Food(BaseModel):
    id: str
    name: str
    alias: str | None = None
    source: str
    source_ref: str | None
    category_id: str
    macros: Macros
    density_g_ml: float | None
    grams_per_unit: float | None
    corrected: bool
    nutrients: dict[str, float] = {}
    provenance: str | None = None
    micros_from: str | None = None
    micros_from_label: str | None = None
    borrowed: list[str] = []
    edible_fraction: float | None = None
    portions: list[Portion] = []
    nutrients_per: str = "100g"
    unit_name: str | None = None
    replaced_by: str | None = None
    archived: bool = False

    @property
    def label(self) -> str:
        return self.alias or self.name

    @property
    def per_unit(self) -> bool:
        return self.nutrients_per == "unit"

    @property
    def per_label(self) -> str:
        return self.unit_name if self.per_unit and self.unit_name else "100 g"


class CandidateOut(BaseModel):
    source: str
    source_ref: str
    name: str
    brand: str | None
    macros: Macros
    category_hint: str
    nutrients: dict[str, float] = {}
    known_id: str | None = None


class SearchOut(BaseModel):
    candidates: list[CandidateOut]
    failed: list[dict[str, str]] = []
    discarded: list[dict[str, str]] = []


class _Measures(BaseModel):
    density_g_ml: float | None = Field(default=None, gt=0, lt=3)
    grams_per_unit: float | None = Field(default=None, gt=0, le=5000)
    portions: list[Portion] = Field(default_factory=list, max_length=20, description=PORTIONS_HELP)
    edible_fraction: float | None = Field(default=None, gt=0, le=1, description=EDIBLE_HELP)
    micros_from: str | None = Field(
        default=None, min_length=36, max_length=36, description=MICROS_FROM_HELP
    )

    @field_validator("portions")
    @classmethod
    def _portions(cls, portions: list[Portion]) -> list[Portion]:
        return _distinct(portions)


class ImportIn(_Measures):
    source: str = Field(pattern="^(usda|off)$")
    source_ref: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    category_id: str = Field(min_length=2, max_length=30)
    macros: MacrosIn
    alias: str | None = Field(default=None, max_length=60, description=ALIAS_HELP)
    nutrients: dict[str, float] = Field(
        default_factory=dict,
        description="The candidate's `nutrients`, as the search returned them.",
    )


class ManualIn(_Measures):
    name: str = Field(min_length=1, max_length=120)
    category_id: str = Field(min_length=2, max_length=30)
    macros: MacrosIn
    alias: str | None = Field(default=None, max_length=60, description=ALIAS_HELP)
    nutrients: dict[str, Any] = Field(default_factory=dict, description=NUTRIENTS_HELP)
    provenance: str | None = Field(default=None, max_length=120, description=PROVENANCE_HELP)
    per_unit: str | None = Field(
        default=None, min_length=1, max_length=30, description=PER_UNIT_HELP
    )

    @field_validator("nutrients")
    @classmethod
    def _nutrients(cls, values: dict[str, Any]) -> dict[str, float]:
        return _typed(values)

    @model_validator(mode="after")
    def _per_unit_borrows_nothing(self) -> ManualIn:
        if self.per_unit and self.micros_from:
            raise ValueError("a per-unit food does not take micros from another, which are per 100 g")
        return self


class AliasIn(BaseModel):
    alias: str | None = Field(default=None, max_length=60, description=ALIAS_HELP)


class CorrectionIn(BaseModel):
    macros: MacrosIn | None = None
    density_g_ml: float | None = Field(default=None, gt=0, lt=3)
    grams_per_unit: float | None = Field(default=None, gt=0, le=5000)
    nutrients: dict[str, Any] = Field(
        default_factory=dict,
        description=NUTRIENTS_HELP
        + " They merge with what it has: a new key is added, an existing one is changed and "
        "one with `null` is removed.",
    )
    provenance: str | None = Field(default=None, max_length=120, description=PROVENANCE_HELP)
    portions: list[Portion] | None = Field(
        default=None,
        max_length=20,
        description=PORTIONS_HELP + " Replaces the whole list; `[]` removes them all.",
    )
    edible_fraction: float | None = Field(default=None, gt=0, le=1, description=EDIBLE_HELP)
    micros_from: str | None = Field(
        default=None,
        min_length=36,
        max_length=36,
        description=MICROS_FROM_HELP + " `null` stops borrowing them.",
    )

    @field_validator("nutrients")
    @classmethod
    def _nutrients(cls, values: dict[str, Any]) -> dict[str, Any]:
        kept = {key: value for key, value in values.items() if value is not None}
        dropped = {key: None for key, value in values.items() if value is None}
        unknown = [key for key in dropped if key not in arga_nutrients.KEYS]
        if unknown:
            raise ValueError(f"'{unknown[0]}' is not an arga nutrient (see `list_nutrients`)")
        return {**_typed(kept), **dropped}

    @field_validator("portions")
    @classmethod
    def _portions(cls, portions: list[Portion] | None) -> list[Portion] | None:
        return None if portions is None else _distinct(portions)


FOLD = str.maketrans(
    "\u00e1\u00e0\u00e2\u00e4\u00e3\u00e9\u00e8\u00ea\u00eb\u00ed\u00ec\u00ee\u00ef\u00f3\u00f2\u00f4\u00f6\u00f5\u00fa\u00f9\u00fb\u00fc\u00f1\u00e7",
    "aaaaaeeeeiiiiooooouuuunc",
)


def fold(value: str | None) -> str:
    return (value or "").lower().translate(FOLD)


def closeness(query: str, *names: str | None) -> int | None:
    wanted = fold(query.strip())
    folded = [fold(one) for one in names if one]
    if not wanted:
        return 0
    if any(one == wanted for one in folded):
        return 0
    if any(one.startswith(wanted) for one in folded):
        return 1
    if any(f" {wanted}" in f" {one}" for one in folded):
        return 2
    if any(wanted in one for one in folded):
        return 3
    return None


def literal(param: str) -> str:
    folded = f"recipes.fold(cast(:{param} as text))"
    return rf"replace(replace(replace({folded}, '\', '\\'), '%', '\%'), '_', '\_')"


def rank(*columns: str) -> str:
    query = literal("query")
    folded = [f"coalesce(recipes.fold({column}), '')" for column in columns]
    exact = " or ".join(f"{one} = {query}" for one in folded)
    starts = " or ".join(f"{one} like {query} || '%'" for one in folded)
    word = " or ".join(f"' ' || {one} like '% ' || {query} || '%'" for one in folded)
    return (
        f"case when cast(:query as text) is null then 0 when {exact} then 0 "
        f"when {starts} then 1 when {word} then 2 else 3 end"
    )


SELECT = """
    select id, name, alias, source, source_ref, category_id, kcal_100g, protein_100g, fat_100g,
           carbs_100g, fiber_100g, salt_100g, density_g_ml, grams_per_unit, corrected,
           nutrients, provenance, micros_from, edible_fraction, nutrients_per, unit_name,
           replaced_by, archived_at,
           (select coalesce(lender.alias, lender.name) from recipes.recipes_food lender
             where lender.id = recipes_food.micros_from) as micros_from_label,
           (select lender.nutrients from recipes.recipes_food lender
             where lender.id = recipes_food.micros_from) as lent,
           (select coalesce(jsonb_agg(jsonb_build_object('name', p.name, 'grams', p.grams)
                                      order by p.grams), '[]'::jsonb)
              from recipes.recipes_food_portion p
             where p.food_id = recipes_food.id) as portions
    from recipes.recipes_food
"""

LIST = text(
    SELECT
    + """
    where archived_at is null
      and (cast(:query as text) is null
           or recipes.fold(name) like '%' || """
    + literal("query")
    + """ || '%'
           or recipes.fold(alias) like '%' || """
    + literal("query")
    + """ || '%')
    order by """
    + rank("coalesce(alias, name)", "name")
    + """, lower(coalesce(alias, name))
    limit :limit
"""
)
BY_ID = text(SELECT + " where id = cast(:id as uuid)")
BY_SOURCE = text(SELECT + " where source = :source and source_ref = :ref")

INSERT = text("""
    insert into recipes.recipes_food
        (name, alias, source, source_ref, category_id, kcal_100g, protein_100g, fat_100g,
         carbs_100g, fiber_100g, salt_100g, density_g_ml, grams_per_unit, corrected, nutrients,
         nutrients_checked_at)
    values (:name, :alias, :source, :source_ref, :category_id, :kcal, :protein, :fat, :carbs,
            :fiber, :salt, :density, :grams_per_unit, :corrected, cast(:nutrients as jsonb),
            case when cast(:nutrients as jsonb) is null then null else now() end)
    returning id
""")

CORRECT = text("""
    update recipes.recipes_food
       set kcal_100g = :kcal, protein_100g = :protein, fat_100g = :fat, carbs_100g = :carbs,
           fiber_100g = :fiber, salt_100g = :salt, density_g_ml = :density,
           grams_per_unit = :grams_per_unit, nutrients = cast(:nutrients as jsonb),
           nutrients_checked_at = case when cast(:nutrients as jsonb) is null
                                       then nutrients_checked_at
                                       else coalesce(nutrients_checked_at, now()) end,
           provenance = :provenance, edible_fraction = :edible_fraction,
           micros_from = cast(:micros_from as uuid), corrected = corrected or :corrected
     where id = cast(:id as uuid)
     returning id
""")

SET_EXTRAS = text("""
    update recipes.recipes_food
       set provenance = :provenance, edible_fraction = :edible_fraction,
           micros_from = cast(:micros_from as uuid), nutrients_per = :nutrients_per,
           unit_name = :unit_name
     where id = cast(:id as uuid)
""")

DROP_PORTIONS = text("delete from recipes.recipes_food_portion where food_id = cast(:id as uuid)")
ADD_PORTION = text("""
    insert into recipes.recipes_food_portion (food_id, name, grams)
    values (cast(:id as uuid), :name, :grams)
""")

LENDER = text("""
    select id, micros_from, nutrients_per from recipes.recipes_food
     where id = cast(:id as uuid)
""")

CATEGORY_EXISTS = text("select 1 from recipes.recipes_food_category where id = :id")

SET_ALIAS = text("""
    update recipes.recipes_food set alias = :alias where id = cast(:id as uuid) returning id
""")

ALIAS_TAKEN = text("""
    select name from recipes.recipes_food
     where lower(btrim(alias)) = lower(btrim(:alias))
       and (cast(:id as uuid) is null or id <> cast(:id as uuid))
     limit 1
""")


def _food(row: Any) -> Food:
    macros = nutrition.Per100g(
        kcal=float(row.kcal_100g),
        protein=float(row.protein_100g),
        fat=float(row.fat_100g),
        carbs=float(row.carbs_100g),
        fiber=None if row.fiber_100g is None else float(row.fiber_100g),
        salt=None if row.salt_100g is None else float(row.salt_100g),
    )
    own = nutrition.per_100g(row.nutrients, macros)
    everything = nutrition.per_100g(row.nutrients, macros, lent=row.lent)
    return Food(
        id=str(row.id),
        name=row.name,
        alias=row.alias,
        source=row.source,
        source_ref=row.source_ref,
        category_id=row.category_id,
        macros=Macros(
            kcal=macros.kcal,
            protein=macros.protein,
            fat=macros.fat,
            carbs=macros.carbs,
            fiber=macros.fiber,
            salt=macros.salt,
        ),
        density_g_ml=None if row.density_g_ml is None else float(row.density_g_ml),
        grams_per_unit=None if row.grams_per_unit is None else float(row.grams_per_unit),
        corrected=row.corrected,
        nutrients=everything,
        provenance=row.provenance,
        micros_from=None if row.micros_from is None else str(row.micros_from),
        micros_from_label=row.micros_from_label,
        borrowed=sorted(set(everything) - set(own)),
        edible_fraction=None if row.edible_fraction is None else float(row.edible_fraction),
        portions=[Portion(name=one["name"], grams=float(one["grams"])) for one in row.portions],
        nutrients_per=row.nutrients_per,
        unit_name=row.unit_name,
        replaced_by=None if row.replaced_by is None else str(row.replaced_by),
        archived=row.archived_at is not None,
    )


async def catalogue(connection: AsyncConnection, query: str | None, limit: int = 200) -> list[Food]:
    rows = (await connection.execute(LIST, {"query": query, "limit": limit})).all()
    return [_food(row) for row in rows]


async def read(connection: AsyncConnection, food_id: str) -> Food:
    row = (await connection.execute(BY_ID, {"id": food_id})).first()
    if row is None:
        raise NotFound(f"el alimento {food_id}")
    return _food(row)


async def _known(connection: AsyncConnection, source: str, ref: str) -> str | None:
    row = (await connection.execute(BY_SOURCE, {"source": source, "ref": ref})).first()
    if row is None:
        return None
    return str(row.replaced_by) if row.replaced_by is not None else str(row.id)


async def search(
    connection: AsyncConnection,
    query: str,
    client: httpx.AsyncClient,
    found: dict[str, Any] | None = None,
) -> SearchOut:
    if found is None:
        found = await hub.search(client, query)
    failed: list[dict[str, str]] = list(found.get("failed") or [])
    discarded: list[dict[str, str]] = list(found.get("discarded") or [])

    out = []
    for raw in found.get("candidates") or []:
        try:
            candidate = sources.Candidate.from_hub(raw)
            macros = Macros(
                kcal=candidate.kcal_100g,
                protein=candidate.protein_100g,
                fat=candidate.fat_100g,
                carbs=candidate.carbs_100g,
                fiber=candidate.fiber_100g,
                salt=candidate.salt_100g,
            )
        except (TypeError, ValidationError) as error:
            discarded.append(_discarded(raw, error))
            continue
        out.append(
            CandidateOut(
                source=candidate.source,
                source_ref=candidate.source_ref,
                name=candidate.name,
                brand=candidate.brand,
                macros=macros,
                category_hint=candidate.category_hint,
                nutrients=arga_nutrients.only_known(candidate.nutrients),
                known_id=await _known(connection, candidate.source, candidate.source_ref),
            )
        )
    return SearchOut(candidates=out, failed=failed, discarded=discarded)


def _discarded(raw: Any, error: Exception) -> dict[str, str]:
    raw = raw if isinstance(raw, dict) else {}
    if isinstance(error, ValidationError) and error.errors():
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        reason = f"{field} = {first.get('input')}: out of range"
    else:
        reason = "it lacks what is needed"
    return {
        "source": str(raw.get("source") or "?"),
        "name": str(raw.get("name") or "?"),
        "reason": reason,
    }


async def _check_category(connection: AsyncConnection, category_id: str) -> None:
    if (await connection.execute(CATEGORY_EXISTS, {"id": category_id})).first() is None:
        raise NotFound(f"category '{category_id}'")


def _stored(values: dict[str, float] | None) -> str | None:
    known = arga_nutrients.only_known(values or {})
    return json.dumps(known) if known else None


def _clean(alias: str | None) -> str | None:
    return (alias or "").strip() or None


async def _check_alias(connection: AsyncConnection, alias: str | None, food_id: str | None) -> None:
    if alias is None:
        return
    taken = (await connection.execute(ALIAS_TAKEN, {"alias": alias, "id": food_id})).first()
    if taken is not None:
        raise Conflict(f"'{alias}' is already the alias of {taken.name}")


async def _check_lender(
    connection: AsyncConnection, lender: str | None, food_id: str | None
) -> None:
    if lender is None:
        return
    if lender == food_id:
        raise Conflict("a food cannot take micros from itself")
    row = (await connection.execute(LENDER, {"id": lender})).first() if _is_uuid(lender) else None
    if row is None:
        raise NotFound(f"food {lender} to take the micros from")
    if row.micros_from is not None:
        raise Conflict("that food already takes its micros from another: point to the original")
    if row.nutrients_per != "100g":
        raise Conflict("that food is per unit: its micros cannot be lent per 100 g")


async def _set_portions(connection: AsyncConnection, food_id: str, portions: list[Portion]) -> None:
    await connection.execute(DROP_PORTIONS, {"id": food_id})
    for one in portions:
        await connection.execute(
            ADD_PORTION, {"id": food_id, "name": one.name.strip(), "grams": one.grams}
        )


async def _insert(connection: AsyncConnection, request: Any, source: str, ref: str | None) -> Food:
    await _check_category(connection, request.category_id)
    alias = _clean(request.alias)
    await _check_alias(connection, alias, None)
    await _check_lender(connection, request.micros_from, None)
    row = (
        await connection.execute(
            INSERT,
            {
                "name": request.name.strip(),
                "alias": alias,
                "source": source,
                "source_ref": ref,
                "category_id": request.category_id,
                "kcal": request.macros.kcal,
                "protein": request.macros.protein,
                "fat": request.macros.fat,
                "carbs": request.macros.carbs,
                "fiber": request.macros.fiber,
                "salt": request.macros.salt,
                "density": request.density_g_ml,
                "grams_per_unit": request.grams_per_unit,
                "corrected": source == "manual",
                "nutrients": _stored(getattr(request, "nutrients", None)),
            },
        )
    ).one()
    food_id = str(row.id)
    await connection.execute(
        SET_EXTRAS,
        {
            "id": food_id,
            "provenance": _clean(getattr(request, "provenance", None)),
            "edible_fraction": request.edible_fraction,
            "micros_from": request.micros_from,
            "nutrients_per": "unit" if getattr(request, "per_unit", None) else "100g",
            "unit_name": (getattr(request, "per_unit", None) or "").strip() or None,
        },
    )
    await _set_portions(connection, food_id, request.portions)
    return await read(connection, food_id)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


async def import_food(connection: AsyncConnection, request: ImportIn) -> Food:
    existing = await _known(connection, request.source, request.source_ref)
    if existing:
        if _clean(request.alias):
            await set_alias(connection, existing, AliasIn(alias=request.alias))
        mine = request.model_fields_set & {"portions", "edible_fraction", "micros_from"}
        if mine:
            await correct(
                connection,
                existing,
                CorrectionIn.model_validate({field: getattr(request, field) for field in mine}),
            )
        return await read(connection, existing)
    return await _insert(connection, request, request.source, request.source_ref)


async def create_manual(connection: AsyncConnection, request: ManualIn) -> Food:
    return await _insert(connection, request, "manual", None)


async def set_alias(connection: AsyncConnection, food_id: str, request: AliasIn) -> Food:
    alias = _clean(request.alias)
    await _check_alias(connection, alias, food_id)
    row = (await connection.execute(SET_ALIAS, {"id": food_id, "alias": alias})).first()
    if row is None:
        raise NotFound(f"el alimento {food_id}")
    return await read(connection, food_id)


async def correct(connection: AsyncConnection, food_id: str, request: CorrectionIn) -> Food:
    current = (await connection.execute(BY_ID, {"id": food_id})).first()
    if current is None:
        raise NotFound(f"el alimento {food_id}")
    sent = request.model_fields_set
    macros = request.macros or Macros(
        kcal=float(current.kcal_100g),
        protein=float(current.protein_100g),
        fat=float(current.fat_100g),
        carbs=float(current.carbs_100g),
        fiber=None if current.fiber_100g is None else float(current.fiber_100g),
        salt=None if current.salt_100g is None else float(current.salt_100g),
    )
    nutrients = arga_nutrients.only_known(current.nutrients or {})
    for key, value in request.nutrients.items():
        if value is None:
            nutrients.pop(key, None)
        else:
            nutrients[key] = value
    micros_from = (
        request.micros_from
        if "micros_from" in sent
        else (None if current.micros_from is None else str(current.micros_from))
    )
    if "micros_from" in sent:
        if micros_from is not None and current.nutrients_per != "100g":
            raise Conflict("a per-unit food does not take micros from another, which are per 100 g")
        await _check_lender(connection, micros_from, food_id)

    def kept(field: str, column: Any) -> Any:
        return getattr(request, field) if field in sent else column

    await connection.execute(
        CORRECT,
        {
            "id": food_id,
            "kcal": macros.kcal,
            "protein": macros.protein,
            "fat": macros.fat,
            "carbs": macros.carbs,
            "fiber": macros.fiber,
            "salt": macros.salt,
            "density": kept("density_g_ml", current.density_g_ml),
            "grams_per_unit": kept("grams_per_unit", current.grams_per_unit),
            "nutrients": json.dumps(nutrients) if nutrients else None,
            "provenance": _clean(kept("provenance", current.provenance)),
            "edible_fraction": kept("edible_fraction", current.edible_fraction),
            "micros_from": micros_from,
            "corrected": bool({"macros", "nutrients"} & sent),
        },
    )
    if request.portions is not None:
        await _set_portions(connection, food_id, request.portions)
    return await read(connection, food_id)


__all__ = [
    "AliasIn",
    "CandidateOut",
    "Conflict",
    "CorrectionIn",
    "Food",
    "ImportIn",
    "Macros",
    "MacrosIn",
    "ManualIn",
    "Portion",
    "SearchOut",
    "catalogue",
    "correct",
    "create_manual",
    "import_food",
    "read",
    "search",
    "set_alias",
]
