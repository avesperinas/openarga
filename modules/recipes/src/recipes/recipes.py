from __future__ import annotations

import json
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import CURRENT_USER_SQL as ME
from recipes import gantt, grid, nutrition


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Category(BaseModel):
    id: str
    name: str
    emoji: str
    position: int


class RecipeSummary(BaseModel):
    id: str
    name: str
    servings: int
    version: int
    tags: list[str]
    total_minutes: int | None = None
    active_minutes: int | None = None
    space_id: str | None = None
    mine: bool = True
    archived: bool = False


CATEGORIES = text("""
    select id, name, emoji, position
    from recipes.recipes_food_category
    order by position
""")

RECIPES = text(f"""
    select r.id,
           r.name,
           r.servings,
           v.number as version,
           v.total_minutes,
           v.active_minutes,
           r.space_id::text as space_id,
           r.user_id = {ME} as mine,
           coalesce(
               array_agg(t.name order by t.name) filter (where t.name is not null),
               '{{}}'
           ) as tags
    from recipes.recipes_recipe r
    join recipes.recipes_recipe_version v on v.id = r.current_version_id
    left join recipes.recipes_recipe_tag rt on rt.recipe_id = r.id
    left join recipes.recipes_tag t on t.id = rt.tag_id
    where (r.archived_at is not null) = :archived
    group by r.id, r.name, r.servings, v.number, v.total_minutes, v.active_minutes, r.space_id,
             r.user_id, r.archived_at
    order by case when :archived then r.archived_at end desc nulls last, lower(r.name)
""")


async def categories(connection: AsyncConnection) -> list[Category]:
    rows = (await connection.execute(CATEGORIES)).all()
    return [
        Category(id=row.id, name=row.name, emoji=row.emoji, position=row.position) for row in rows
    ]


async def recipes(connection: AsyncConnection, archived: bool = False) -> list[RecipeSummary]:
    rows = (await connection.execute(RECIPES, {"archived": archived})).all()
    return [
        RecipeSummary(
            id=str(row.id),
            name=row.name,
            servings=row.servings,
            version=row.version,
            tags=list(row.tags),
            total_minutes=row.total_minutes,
            active_minutes=row.active_minutes,
            space_id=row.space_id,
            mine=bool(row.mine),
            archived=archived,
        )
        for row in rows
    ]


ARCHIVE = text("""
    update recipes.recipes_recipe
       set archived_at = case when :archive then coalesce(archived_at, now()) end
     where id = cast(:id as uuid)
""")


async def archive(connection: AsyncConnection, recipe_id: str, archived: bool = True) -> None:
    found = (await connection.execute(OWNER_OF, {"id": recipe_id})).first()
    if found is None:
        raise NotFound(f"la receta {recipe_id}")
    if not found.mine:
        raise Conflict("solo quien creó la receta la archiva")
    await connection.execute(ARCHIVE, {"id": recipe_id, "archive": archived})


MAX_INGREDIENTS = 60


class IngredientIn(BaseModel):
    food_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(pattern="^(g|ml|unit|tbsp|tsp|pinch)$")
    note: str | None = Field(default=None, max_length=120)
    optional: bool = False
    portion: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        description=(
            'Con `unit: "unit"`, qué medida de casa del alimento cuenta la cantidad: '
            '`quantity: 2, unit: "unit", portion: "loncha"`. Sin ella, la de por defecto '
            "(`grams_per_unit`)."
        ),
    )
    as_purchased: bool = Field(
        default=False,
        description=(
            "La cantidad es en bruto, con lo que no se come (espina, piel, hueso): se le aplica "
            "la parte comestible del alimento (`edible_fraction`)."
        ),
    )

    @model_validator(mode="after")
    def _one_or_the_other(self) -> IngredientIn:
        if (self.food_id is None) == (self.name is None):
            raise ValueError("un ingrediente lleva `food_id` o `name`, nunca los dos ni ninguno")
        if self.portion is not None and self.unit != "unit":
            raise ValueError('una porción cuenta unidades: va con `unit: "unit"`')
        return self


Action = Literal[
    "wash",
    "peel",
    "chop",
    "mix",
    "knead",
    "season",
    "coat",
    "fry",
    "saute",
    "boil",
    "simmer",
    "steam",
    "bake",
    "roast",
    "grill",
    "toast",
    "rest",
    "marinate",
    "chill",
    "freeze",
    "prove",
    "blend",
    "strain",
    "assemble",
    "serve",
]
Equipment = Literal["hob", "oven", "air_fryer", "board", "bowl", "fridge", "none"]
ACTIONS: tuple[str, ...] = get_args(Action)
EQUIPMENT: tuple[str, ...] = get_args(Equipment)
MAX_STEPS = 40


class StepIn(BaseModel):
    action: Action = Field(description="El verbo del paso.")
    text: str = Field(min_length=1, max_length=200)
    minutes: int = Field(ge=1, le=2880)
    attended: bool = True
    equipment: Equipment = Field(
        default="none",
        description=(
            "Dónde pasa: es el carril del diagrama. `none` es lo que no ocupa nada (un reposo)."
        ),
    )
    after: list[int] = Field(
        default_factory=list,
        max_length=MAX_STEPS,
        description=(
            "Los pasos que tienen que estar hechos antes, por su posición en `steps` contando "
            "desde 1: el primer paso es el 1. Solo anteriores a este."
        ),
    )
    ingredients: list[int] = Field(
        default_factory=list,
        max_length=MAX_INGREDIENTS,
        description=(
            "Los ingredientes que entran en este paso, por su posición en `ingredients` contando "
            "desde 1: el primer ingrediente es el 1."
        ),
    )


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    servings: int = Field(ge=1, le=50)
    ingredients: list[IngredientIn] = Field(min_length=1, max_length=MAX_INGREDIENTS)
    steps: list[StepIn] = Field(default_factory=list, max_length=MAX_STEPS)
    tags: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _steps_point_backwards(self) -> RecipeIn:
        for position, step in enumerate(self.steps, start=1):
            for after in step.after:
                if after >= position:
                    raise ValueError(
                        f"el paso {position} depende del {after}, que no va antes: un paso solo "
                        f"puede depender de los anteriores"
                    )
            for reference in step.ingredients:
                if not 1 <= reference <= len(self.ingredients):
                    raise ValueError(
                        f"el paso {position} usa el ingrediente {reference} y solo hay "
                        f"{len(self.ingredients)}"
                    )
        return self


INSERT_RECIPE = text("""
    insert into recipes.recipes_recipe (name, servings) values (:name, :servings)
    returning id
""")

RENAME_RECIPE = text("""
    update recipes.recipes_recipe set name = :name, servings = :servings
     where id = cast(:id as uuid)
     returning id
""")

NEXT_NUMBER = text("""
    select coalesce(max(number), 0) + 1 as number
    from recipes.recipes_recipe_version where recipe_id = cast(:recipe as uuid)
""")

SPACE_OF = text(
    "select space_id::text from recipes.recipes_recipe where id = cast(:recipe as uuid)"
)

INSERT_VERSION = text("""
    insert into recipes.recipes_recipe_version
        (recipe_id, number, source, servings, note, space_id)
    values (cast(:recipe as uuid), :number, :source, :servings, :note, cast(:space as uuid))
    returning id, number
""")

INSERT_STEP = text("""
    insert into recipes.recipes_step
        (version_id, position, action, text, minutes, attended, equipment, space_id)
    values (cast(:version as uuid), :position, :action, :text, :minutes, :attended, :equipment,
            cast(:space as uuid))
""")

INSERT_DEPENDENCY = text("""
    insert into recipes.recipes_step_dependency
        (version_id, step_position, after_position, space_id)
    values (cast(:version as uuid), :step, :after, cast(:space as uuid))
    on conflict do nothing
""")

INSERT_STEP_INGREDIENT = text("""
    insert into recipes.recipes_step_ingredient
        (version_id, step_position, ingredient_id, space_id)
    values (cast(:version as uuid), :step, cast(:ingredient as uuid), cast(:space as uuid))
    on conflict do nothing
""")

INSERT_INGREDIENT = text("""
    insert into recipes.recipes_recipe_ingredient
        (version_id, position, food_id, unresolved_name, quantity, unit, note, optional, space_id,
         portion, as_purchased)
    values (cast(:version as uuid), :position, cast(:food as uuid), :unresolved,
            :quantity, :unit, :note, :optional, cast(:space as uuid), :portion, :as_purchased)
    returning id
""")

FOODS_TO_SPACE = text(f"""
    update recipes.recipes_food f set space_id = cast(:space as uuid)
     where f.space_id is null and f.user_id = {ME}
       and f.id in (
           select i.food_id from recipes.recipes_recipe_ingredient i
           join recipes.recipes_recipe_version v on v.id = i.version_id
           where v.recipe_id = cast(:recipe as uuid) and i.food_id is not null
       )
""")

SEAL = text("""
    update recipes.recipes_recipe_version
       set sealed_at = now(), total_minutes = :total, active_minutes = :active
     where id = cast(:id as uuid)
""")

POINT_AT = text("""
    update recipes.recipes_recipe set current_version_id = cast(:version as uuid)
     where id = cast(:recipe as uuid)
""")

FOOD_BY_NAME = text(f"""
    select id from recipes.recipes_food
     where archived_at is null
       and (lower(btrim(alias)) = lower(btrim(:name)) or lower(btrim(name)) = lower(btrim(:name)))
     order by coalesce(lower(btrim(alias)) = lower(btrim(:name)), false) desc,
              -- Lo tuyo antes que lo de un espacio: tu receta no depende de él si puede no
              -- hacerlo (ADR-0121).
              coalesce(user_id = {ME}, false) desc, imported_at
     limit 1
""")

FOOD_EXISTS = text("select replaced_by from recipes.recipes_food where id = cast(:id as uuid)")

TAG_BY_NAME = text("""
    select id from recipes.recipes_tag where lower(btrim(name)) = lower(btrim(:name))
""")

INSERT_TAG = text("insert into recipes.recipes_tag (name) values (:name) returning id")

CLEAR_TAGS = text("delete from recipes.recipes_recipe_tag where recipe_id = cast(:id as uuid)")

LINK_TAG = text("""
    insert into recipes.recipes_recipe_tag (recipe_id, tag_id)
    values (cast(:recipe as uuid), cast(:tag as uuid))
""")

ENQUEUE = text("""
    insert into recipes.recipes_outbox (type, payload, dedup_hash)
    values (:type, cast(:payload as jsonb), :dedup)
    on conflict do nothing
""")

RECIPE_ROW = text(f"""
    select r.id, r.name, r.servings, r.current_version_id, v.number, v.source, v.note,
           v.created_at, r.space_id::text as space_id, r.user_id = {ME} as mine,
           r.archived_at is not null as archived,
           (select count(*) from recipes.recipes_recipe_version other
             where other.recipe_id = r.id and other.sealed_at is not null) as versions
    from recipes.recipes_recipe r
    join recipes.recipes_recipe_version v on v.id = r.current_version_id
    where r.id = cast(:id as uuid)
""")

INGREDIENTS_OF = text("""
    select i.position, i.quantity, i.unit, i.note, i.optional, i.unresolved_name,
           f.id as food_id, coalesce(f.alias, f.name) as food_name, f.category_id,
           f.kcal_100g, f.protein_100g, f.fat_100g, f.carbs_100g, f.fiber_100g, f.salt_100g,
           f.density_g_ml, f.grams_per_unit, f.nutrients, f.edible_fraction,
           f.nutrients_per, i.portion, i.as_purchased,
           (select lender.nutrients from recipes.recipes_food lender
             where lender.id = f.micros_from) as lent,
           (select coalesce(jsonb_object_agg(lower(p.name), p.grams), '{}'::jsonb)
              from recipes.recipes_food_portion p where p.food_id = f.id) as portions
    from recipes.recipes_recipe_ingredient i
    left join recipes.recipes_food f on f.id = i.food_id
    where i.version_id = cast(:version as uuid)
    order by i.position
""")

STEPS_OF = text("""
    select s.position, s.action, s.text, s.minutes, s.attended, s.equipment,
           coalesce(
               array_agg(d.after_position order by d.after_position)
                 filter (where d.after_position is not null),
               '{}'
           ) as after
    from recipes.recipes_step s
    left join recipes.recipes_step_dependency d
      on d.version_id = s.version_id and d.step_position = s.position
    where s.version_id = cast(:version as uuid)
    group by s.position, s.action, s.text, s.minutes, s.attended, s.equipment
    order by s.position
""")

STEP_INGREDIENTS_OF = text("""
    select si.step_position, i.position, coalesce(f.alias, f.name, i.unresolved_name) as name
    from recipes.recipes_step_ingredient si
    join recipes.recipes_recipe_ingredient i on i.id = si.ingredient_id
    left join recipes.recipes_food f on f.id = i.food_id
    where si.version_id = cast(:version as uuid)
    order by si.step_position, i.position
""")

TAGS_OF = text("""
    select t.id, t.name, t.emoji
    from recipes.recipes_recipe_tag rt
    join recipes.recipes_tag t on t.id = rt.tag_id
    where rt.recipe_id = cast(:id as uuid)
    order by lower(t.name)
""")


async def _resolve_food(connection: AsyncConnection, item: IngredientIn) -> str | None:
    if item.food_id is not None:
        found = (await connection.execute(FOOD_EXISTS, {"id": item.food_id})).first()
        if found is None:
            raise NotFound(f"el alimento {item.food_id}")
        return item.food_id if found.replaced_by is None else str(found.replaced_by)
    row = (await connection.execute(FOOD_BY_NAME, {"name": item.name})).first()
    return None if row is None else str(row.id)


async def _tag_id(connection: AsyncConnection, name: str) -> str:
    row = (await connection.execute(TAG_BY_NAME, {"name": name})).first()
    if row is not None:
        return str(row.id)
    created = (await connection.execute(INSERT_TAG, {"name": name.strip()})).one()
    return str(created.id)


async def _write_version(
    connection: AsyncConnection, recipe_id: str, request: RecipeIn, source: str
) -> int:
    number = (await connection.execute(NEXT_NUMBER, {"recipe": recipe_id})).one().number
    space = await connection.scalar(SPACE_OF, {"recipe": recipe_id})
    version = (
        await connection.execute(
            INSERT_VERSION,
            {
                "recipe": recipe_id,
                "number": number,
                "source": source,
                "servings": request.servings,
                "note": request.note,
                "space": space,
            },
        )
    ).one()

    written: dict[int, str] = {}
    for position, item in enumerate(request.ingredients, start=1):
        food = await _resolve_food(connection, item)
        row = await connection.execute(
            INSERT_INGREDIENT,
            {
                "version": str(version.id),
                "position": position,
                "food": food,
                "unresolved": None if food else (item.name or "").strip(),
                "quantity": item.quantity,
                "unit": item.unit,
                "note": item.note,
                "optional": item.optional,
                "space": space,
                "portion": None if item.portion is None else item.portion.strip(),
                "as_purchased": item.as_purchased,
            },
        )
        written[position] = str(row.one().id)

    for position, step in enumerate(request.steps, start=1):
        await connection.execute(
            INSERT_STEP,
            {
                "version": str(version.id),
                "position": position,
                "action": step.action,
                "text": step.text.strip(),
                "minutes": step.minutes,
                "attended": step.attended,
                "equipment": step.equipment,
                "space": space,
            },
        )
        for after in dict.fromkeys(step.after):
            await connection.execute(
                INSERT_DEPENDENCY,
                {"version": str(version.id), "step": position, "after": after, "space": space},
            )
        for reference in dict.fromkeys(step.ingredients):
            await connection.execute(
                INSERT_STEP_INGREDIENT,
                {
                    "version": str(version.id),
                    "step": position,
                    "ingredient": written[reference],
                    "space": space,
                },
            )

    plan = gantt.schedule(
        [
            gantt.Step(
                position=position,
                action=step.action,
                text=step.text,
                minutes=step.minutes,
                attended=step.attended,
                equipment=step.equipment,
                after=tuple(step.after),
            )
            for position, step in enumerate(request.steps, start=1)
        ]
    )

    await connection.execute(
        SEAL,
        {
            "id": str(version.id),
            "total": plan.total_minutes,
            "active": plan.active_minutes,
        },
    )
    await connection.execute(POINT_AT, {"recipe": recipe_id, "version": str(version.id)})
    if space is not None:
        await connection.execute(FOODS_TO_SPACE, {"recipe": recipe_id, "space": space})

    await connection.execute(CLEAR_TAGS, {"id": recipe_id})
    for name in dict.fromkeys(tag.strip() for tag in request.tags if tag.strip()):
        await connection.execute(
            LINK_TAG, {"recipe": recipe_id, "tag": await _tag_id(connection, name)}
        )

    await connection.execute(
        ENQUEUE,
        {
            "type": "recipes.recipe_saved",
            "payload": json.dumps(
                {
                    "recipe_id": recipe_id,
                    "name": request.name,
                    "version": number,
                    "servings": request.servings,
                    "ingredients": len(request.ingredients),
                    "source": source,
                }
            ),
            "dedup": f"recipe:{recipe_id}:v{number}",
        },
    )
    return number


async def create(connection: AsyncConnection, request: RecipeIn, source: str = "app") -> str:
    recipe = (
        await connection.execute(
            INSERT_RECIPE, {"name": request.name.strip(), "servings": request.servings}
        )
    ).one()
    await _write_version(connection, str(recipe.id), request, source)
    return str(recipe.id)


async def update(
    connection: AsyncConnection, recipe_id: str, request: RecipeIn, source: str = "app"
) -> int:
    row = (
        await connection.execute(
            RENAME_RECIPE,
            {"id": recipe_id, "name": request.name.strip(), "servings": request.servings},
        )
    ).first()
    if row is None:
        raise NotFound(f"la receta {recipe_id}")
    return await _write_version(connection, recipe_id, request, source)


class Tag(BaseModel):
    id: str
    name: str
    emoji: str | None


class IngredientOut(BaseModel):
    position: int
    name: str
    food_id: str | None
    category_id: str
    quantity: float
    unit: str
    note: str | None
    optional: bool
    grams: float | None
    portion: str | None = None
    as_purchased: bool = False


class Group(BaseModel):
    category_id: str
    name: str
    emoji: str
    ingredients: list[IngredientOut]


class MacroSet(BaseModel):
    kcal: float
    protein: float
    fat: float
    carbs: float
    fiber: float | None
    salt: float | None


class Nutrition(BaseModel):
    total: MacroSet
    per_serving: MacroSet
    counted: int
    ingredients: int
    uncertainty: str | None
    nutrients: dict[str, float] = {}
    coverage: dict[str, float] = {}


class ScheduledStep(BaseModel):
    position: int
    action: str
    text: str
    minutes: int
    attended: bool
    equipment: str
    ingredients: list[str]
    uses: list[int] = []
    after: list[int] = []
    start: int
    end: int


class GridRow(BaseModel):
    position: int
    name: str
    orphan: bool = False


class GridCell(BaseModel):
    position: int
    action: str
    text: str
    minutes: int
    attended: bool
    equipment: str
    column: int
    row: int
    span: int


class GridBand(BaseModel):
    position: int
    action: str
    text: str
    minutes: int
    attended: bool
    equipment: str


class RecipeGrid(BaseModel):
    rows: list[GridRow]
    cells: list[GridCell]
    bands: list[GridBand]
    columns: int
    notes: list[str]


class Kitchen(BaseModel):
    steps: list[ScheduledStep]
    grid: RecipeGrid
    total_minutes: int
    active_minutes: int
    lanes: list[str]
    overlaps: list[dict]


class Recipe(BaseModel):
    id: str
    name: str
    servings: int
    requested_servings: int
    version: int
    version_id: str
    versions: int
    source: str
    note: str | None
    tags: list[Tag]
    groups: list[Group]
    nutrition: Nutrition
    kitchen: Kitchen
    space_id: str | None = None
    mine: bool = True
    archived: bool = False


CATEGORY_ROWS = text("select id, name, emoji, position from recipes.recipes_food_category")
UNRESOLVED_CATEGORY = "other"


def _macros(total: nutrition.Totals) -> MacroSet:
    return MacroSet(
        kcal=total.kcal,
        protein=total.protein,
        fat=total.fat,
        carbs=total.carbs,
        fiber=total.fiber,
        salt=total.salt,
    )


def _item(row: Any, scale: float) -> tuple[nutrition.Item, IngredientOut]:
    name = row.food_name or row.unresolved_name
    measures = (
        None
        if row.food_id is None
        else nutrition.Convertible(
            density_g_ml=None if row.density_g_ml is None else float(row.density_g_ml),
            grams_per_unit=None if row.grams_per_unit is None else float(row.grams_per_unit),
            portions={key: float(value) for key, value in (row.portions or {}).items()},
            edible_fraction=None if row.edible_fraction is None else float(row.edible_fraction),
        )
    )
    macros = (
        None
        if row.food_id is None
        else nutrition.Per100g(
            kcal=float(row.kcal_100g),
            protein=float(row.protein_100g),
            fat=float(row.fat_100g),
            carbs=float(row.carbs_100g),
            fiber=None if row.fiber_100g is None else float(row.fiber_100g),
            salt=None if row.salt_100g is None else float(row.salt_100g),
        )
    )
    quantity = float(row.quantity)
    item = nutrition.Item(
        quantity=quantity,
        unit=row.unit,
        macros=macros,
        measures=measures,
        label=name,
        nutrients=None if macros is None else nutrition.per_100g(row.nutrients, macros, row.lent),
        portion=row.portion,
        as_purchased=row.as_purchased,
        per_unit=row.nutrients_per == "unit",
    )
    out = IngredientOut(
        position=row.position,
        name=name,
        food_id=None if row.food_id is None else str(row.food_id),
        category_id=row.category_id or UNRESOLVED_CATEGORY,
        quantity=round(quantity * scale, 2),
        unit=row.unit,
        note=row.note,
        optional=row.optional,
        grams=nutrition.to_grams(
            quantity * scale, row.unit, measures, row.portion, row.as_purchased
        ),
        portion=row.portion,
        as_purchased=row.as_purchased,
    )
    return item, out


async def read(connection: AsyncConnection, recipe_id: str, servings: int | None = None) -> Recipe:
    head = (await connection.execute(RECIPE_ROW, {"id": recipe_id})).first()
    if head is None:
        raise NotFound(f"la receta {recipe_id}")

    wanted = servings or head.servings
    if wanted < 1 or wanted > 50:
        raise Conflict("una receta se pide para entre 1 y 50 personas")
    scale = wanted / head.servings

    rows = (
        await connection.execute(INGREDIENTS_OF, {"version": str(head.current_version_id)})
    ).all()
    pairs = [_item(row, scale) for row in rows]
    total = nutrition.totals([item for item, _ in pairs], scale=scale)
    serving = nutrition.per_serving(total, wanted)

    categories = {row.id: row for row in (await connection.execute(CATEGORY_ROWS)).all()}
    ordered = sorted(categories.values(), key=lambda row: row.position)
    groups = []
    for category in ordered:
        inside = [out for _, out in pairs if out.category_id == category.id]
        if inside:
            groups.append(
                Group(
                    category_id=category.id,
                    name=category.name,
                    emoji=category.emoji,
                    ingredients=inside,
                )
            )

    kitchen = await _kitchen(connection, str(head.current_version_id), [out for _, out in pairs])
    tags = (await connection.execute(TAGS_OF, {"id": recipe_id})).all()
    return Recipe(
        id=str(head.id),
        name=head.name,
        servings=head.servings,
        requested_servings=wanted,
        version=head.number,
        version_id=str(head.current_version_id),
        versions=head.versions,
        source=head.source,
        note=head.note,
        tags=[Tag(id=str(row.id), name=row.name, emoji=row.emoji) for row in tags],
        groups=groups,
        nutrition=Nutrition(
            total=_macros(total),
            per_serving=_macros(serving),
            counted=total.counted,
            ingredients=total.total,
            uncertainty=nutrition.uncertainty(total),
            nutrients=serving.nutrients,
            coverage=serving.coverage,
        ),
        kitchen=kitchen,
        space_id=head.space_id,
        mine=bool(head.mine),
        archived=bool(head.archived),
    )


async def _kitchen(
    connection: AsyncConnection, version_id: str, ingredients: list[IngredientOut]
) -> Kitchen:
    rows = (await connection.execute(STEPS_OF, {"version": version_id})).all()
    used = (await connection.execute(STEP_INGREDIENTS_OF, {"version": version_id})).all()
    by_step: dict[int, list[str]] = {}
    positions: dict[int, list[int]] = {}
    for row in used:
        by_step.setdefault(row.step_position, []).append(row.name)
        positions.setdefault(row.step_position, []).append(row.position)

    steps = [
        gantt.Step(
            position=row.position,
            action=row.action,
            text=row.text,
            minutes=row.minutes,
            attended=row.attended,
            equipment=row.equipment,
            after=tuple(row.after),
            ingredients=tuple(by_step.get(row.position, [])),
            uses=tuple(positions.get(row.position, [])),
        )
        for row in rows
    ]
    by_position = {one.position: one for one in steps}
    plan = gantt.schedule(steps)
    drawn = grid.build(steps, [grid.Ingredient(one.position, one.name) for one in ingredients])
    return Kitchen(
        steps=[
            ScheduledStep(
                position=one.position,
                action=one.action,
                text=one.text,
                minutes=one.minutes,
                attended=one.attended,
                equipment=one.equipment,
                ingredients=list(one.ingredients),
                uses=list(positions.get(one.position, [])),
                after=list(by_position[one.position].after),
                start=one.start,
                end=one.end,
            )
            for one in plan.steps
        ],
        grid=RecipeGrid(
            rows=[GridRow(**vars(one)) for one in drawn.rows],
            cells=[GridCell(**vars(one)) for one in drawn.cells],
            bands=[GridBand(**vars(one)) for one in drawn.bands],
            columns=drawn.columns,
            notes=list(drawn.notes),
        ),
        total_minutes=plan.total_minutes,
        active_minutes=plan.active_minutes,
        lanes=list(plan.lanes),
        overlaps=[
            {"equipment": clash.equipment, "positions": clash.positions}
            for clash in gantt.overlaps(plan)
        ],
    )


DELETE_RECIPE = text("delete from recipes.recipes_recipe where id = cast(:id as uuid)")


OWNER_OF = text(f"""
    select space_id::text as space_id, user_id = {ME} as mine
    from recipes.recipes_recipe where id = cast(:id as uuid)
""")


async def remove(connection: AsyncConnection, recipe_id: str) -> None:
    found = (await connection.execute(OWNER_OF, {"id": recipe_id})).first()
    if found is not None and found.space_id is not None and not found.mine:
        raise Conflict("esta receta la compartió otra persona: solo ella la borra")
    if (await connection.execute(DELETE_RECIPE, {"id": recipe_id})).rowcount == 0:
        raise NotFound(f"la receta {recipe_id}")


PARTS = (
    "recipes_recipe_ingredient",
    "recipes_step",
    "recipes_step_dependency",
    "recipes_step_ingredient",
)


def _move(table: str, take: bool) -> str:
    owner = f", user_id = {ME}" if take else ""
    return f"""
        update recipes.{table} set space_id = cast(:space as uuid){owner}
         where version_id in (
             select id from recipes.recipes_recipe_version
             where recipe_id = cast(:id as uuid)
         )
    """


FREE_FOODS = text(f"""
    update recipes.recipes_food f set space_id = null
     where f.user_id = {ME} and f.space_id = cast(:old as uuid)
       and not exists (
           select 1 from recipes.recipes_recipe_ingredient i
           where i.food_id = f.id and i.space_id = f.space_id
       )
""")


async def share(connection: AsyncConnection, recipe_id: str, space_id: str | None) -> None:
    found = (await connection.execute(OWNER_OF, {"id": recipe_id})).first()
    if found is None:
        raise NotFound(f"la receta {recipe_id}")
    if not found.mine:
        raise Conflict("solo quien creó la receta la comparte o deja de compartirla")
    if found.space_id == space_id:
        return
    take = found.space_id is not None
    params = {"id": recipe_id, "space": space_id}
    for table in PARTS:
        await connection.execute(text(_move(table, take)), params)
    owner = f", user_id = {ME}" if take else ""
    await connection.execute(
        text(
            f"update recipes.recipes_recipe_version set space_id = cast(:space as uuid)"
            f"{owner} where recipe_id = cast(:id as uuid)"
        ),
        params,
    )
    await connection.execute(
        text(
            "update recipes.recipes_recipe set space_id = cast(:space as uuid) "
            "where id = cast(:id as uuid)"
        ),
        params,
    )
    if found.space_id is not None:
        await connection.execute(FREE_FOODS, {"old": found.space_id})
    if space_id is not None:
        await connection.execute(FOODS_TO_SPACE, {"recipe": recipe_id, "space": space_id})


ALL_TAGS = text("select id, name, emoji from recipes.recipes_tag order by lower(name)")


async def tags(connection: AsyncConnection) -> list[Tag]:
    rows = (await connection.execute(ALL_TAGS)).all()
    return [Tag(id=str(row.id), name=row.name, emoji=row.emoji) for row in rows]
