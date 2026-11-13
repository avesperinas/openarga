from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import arga_agenda

AGENDA = arga_agenda.KEY
BODY_WEIGHT = "body_weight"
LINKABLE = "linkable"
MENTION = "mention"
ACTIVITY = "activity"
METRIC = "metric"
CUSTODY = "custody"
RECORD = "record"
TRIP = "trip"
WORKOUT = "workout"
CONTRACTS = frozenset(
    {AGENDA, BODY_WEIGHT, LINKABLE, MENTION, ACTIVITY, METRIC, CUSTODY, RECORD, TRIP, WORKOUT}
)

SHOPPING_ADD = "shopping.add"
NOTES_LIST = "notes.list"
NOTES_READ = "notes.read"
NOTES_CREATE = "notes.create"
NOTES_WRITE = "notes.write"
NOTES_TRASH = "notes.trash"
NOTES = frozenset({NOTES_LIST, NOTES_READ, NOTES_CREATE, NOTES_WRITE, NOTES_TRASH})
AGENDA_MOVE = "agenda.move"
PANTRY_SEARCH = "pantry.search"
PANTRY_IMPORT = "pantry.import"
PANTRY_NUTRIENTS = "pantry.nutrients"
RECIPES_SEARCH = "recipes.search"
RECIPES_NUTRIENTS = "recipes.nutrients"
RECIPES_CREATE = "recipes.create"
PANTRY = frozenset(
    {
        PANTRY_SEARCH,
        PANTRY_IMPORT,
        PANTRY_NUTRIENTS,
        RECIPES_SEARCH,
        RECIPES_NUTRIENTS,
        RECIPES_CREATE,
    }
)
WEIGHT_LOG = "weight.log"
TRIPS_IDEA = "trips.idea"
WORKOUT_HEART = "workout.heart"
INTAKE_REPLACE_FOOD = "intake.replace_food"
BOOKS_WANT = "books.want"
SERVICES = (
    frozenset(
        {
            SHOPPING_ADD,
            AGENDA_MOVE,
            WEIGHT_LOG,
            TRIPS_IDEA,
            WORKOUT_HEART,
            INTAKE_REPLACE_FOOD,
            BOOKS_WANT,
        }
    )
    | NOTES
    | PANTRY
)
ADDRESSED = {AGENDA_MOVE: AGENDA}


class BadContract(ValueError):
    pass


def _check(model: type[BaseModel], fields: dict[str, Any]) -> dict[str, Any]:
    try:
        return model.model_validate(fields).model_dump(mode="json")
    except ValidationError as error:
        where = "; ".join(
            f"{'.'.join(str(p) for p in item['loc']) or 'objeto'}: {item['msg']}"
            for item in error.errors()
        )
        raise BadContract(f"{model.__name__} does not match: {where}") from None


class BodyWeight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    day: date
    kg: float = Field(gt=0, le=500)


def body_weight(**fields: Any) -> dict[str, Any]:
    return _check(BodyWeight, fields)


BODY_WEIGHT_DAYS = """
    select day, round(avg(kg), 2) as kg from (
        select distinct on (payload->'body_weight'->>'id')
            (payload->'body_weight'->>'day')::date as day,
            (payload->'body_weight'->>'kg')::numeric as kg
        from {view}
        where payload ? 'body_weight'
        order by payload->'body_weight'->>'id', ts desc, ingested_at desc
    ) as weighing
    group by day
"""


def body_weight_days(view: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*\.events", view):
        raise ValueError(f"'{view}' is not an app's events view")
    return BODY_WEIGHT_DAYS.format(view=view)


class WeightLog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kg: float = Field(ge=20, le=400)
    day: date | None = None


class WeightLogged(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    day: date
    kg: float
    already: bool


def weight_log(**fields: Any) -> dict[str, Any]:
    return _check(WeightLog, fields)


def weight_logged(**fields: Any) -> dict[str, Any]:
    return _check(WeightLogged, fields)


class WorkoutHeartAsk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=200)


class HeartBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    s: int
    bpm: float


class HeartMark(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    at: datetime
    label: str


class WorkoutHeart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    found: bool
    minutes: int = 0
    avg: float | None = None
    max: float | None = None
    zones: list[float] = []
    load: float = 0
    recovery_2min: float | None = None
    source: Literal["band", "day"] | None = None
    kcal: float | None = None
    max_heart_rate: int = 0
    beats: list[HeartBeat] = []
    marks: list[HeartMark] = []


def workout_heart_ask(**fields: Any) -> dict[str, Any]:
    return _check(WorkoutHeartAsk, fields)


def workout_heart(**fields: Any) -> dict[str, Any]:
    return _check(WorkoutHeart, fields)


CUSTODY_CATEGORIES = frozenset({"contract", "document", "insurance", "other"})


class Custody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=40)
    category: str
    href: str = Field(pattern=r"^/[^/]", max_length=500)
    since: date | None = None
    until: date | None = None
    detail: str = Field(default="", max_length=200)
    removed: bool = False

    @model_validator(mode="after")
    def _known_category(self) -> Custody:
        if self.category not in CUSTODY_CATEGORIES:
            raise ValueError(f"category: one of {sorted(CUSTODY_CATEGORIES)}")
        return self


def custody(**fields: Any) -> dict[str, Any]:
    return _check(Custody, fields)


TRIP_PHASES = frozenset({"idea", "plan", "upcoming", "ongoing", "done"})


class Trip(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    phase: str
    href: str = Field(pattern=r"^/[^/]", max_length=500)
    starts_on: date | None = None
    ends_on: date | None = None
    image: str | None = Field(default=None, pattern=r"^/[^/]", max_length=500)
    detail: str = Field(default="", max_length=200)
    removed: bool = False

    @model_validator(mode="after")
    def _known_phase(self) -> Trip:
        if self.phase not in TRIP_PHASES:
            raise ValueError(f"phase: one of {sorted(TRIP_PHASES)}")
        if (self.starts_on is None) != (self.ends_on is None):
            raise ValueError("starts_on and ends_on go together")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("a trip does not end before it starts")
        return self


def trip(**fields: Any) -> dict[str, Any]:
    return _check(Trip, fields)


class TripIdea(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=120)
    place: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _whole_point(self) -> TripIdea:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon go together")
        return self


class TripIdeaMade(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    href: str = Field(pattern=r"^/[^/]")
    already: bool


def trip_idea(**fields: Any) -> dict[str, Any]:
    return _check(TripIdea, fields)


def trip_idea_made(**fields: Any) -> dict[str, Any]:
    return _check(TripIdeaMade, fields)


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=60)
    start: datetime
    minutes: int | None = Field(default=None, ge=0, le=1440)
    tz: str = Field(min_length=1, max_length=64)
    removed: bool = False


def activity(**fields: Any) -> dict[str, Any]:
    found = _check(Activity, fields)
    if datetime.fromisoformat(found["start"]).tzinfo is None:
        raise BadContract("Activity does not match: start: with a time zone")
    return found


class WorkoutMark(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    at: datetime
    label: str = Field(min_length=1, max_length=80)


class Workout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    kind: Literal["strength", "activity"]
    name: str = Field(min_length=1, max_length=60)
    start: datetime
    end: datetime
    tz: str = Field(min_length=1, max_length=64)
    href: str | None = Field(default=None, max_length=200)
    band_id: str | None = Field(default=None, max_length=200)
    marks: list[WorkoutMark] = Field(default=[], max_length=300)
    removed: bool = False

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Workout:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end, with a time zone")
        if self.end < self.start:
            raise ValueError("end before start")
        return self


def workout(**fields: Any) -> dict[str, Any]:
    return _check(Workout, fields)


UNITS = frozenset(
    {
        "EUR",
        "kg",
        "g",
        "mg",
        "µg",
        "kcal",
        "ml",
        "mg/dL",
        "bpm",
        "steps",
        "count",
        "points",
        "percent",
        "ml/kg/min",
        "min",
        "h",
        "km",
        "km/h",
        "m",
        "cm",
        "m/s",
        "ms",
        "dB",
        "MET",
    }
)
METRIC_KEY = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(:[^\s]{1,100})?$"


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=METRIC_KEY, max_length=160)
    label: str = Field(min_length=1, max_length=80)
    unit: str
    kind: str = Field(pattern=r"^(level|amount|peak)$")
    day: date
    value: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def _known_unit(self) -> Metric:
        if self.unit not in UNITS:
            raise ValueError(f"unit: one of {sorted(UNITS)}")
        return self


def metric(app: str, **fields: Any) -> dict[str, Any]:
    found = _check(Metric, fields)
    if found["key"].split(".", 1)[0] != app:
        raise BadContract(f"Metric does not match: key: must start with '{app}.'")
    return found


def metric_identity(point: dict[str, Any]) -> str:
    return f"{point['key']}@{point['day']}"


class Linkable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=40)
    href: str = Field(pattern=r"^/[^/]", max_length=500)
    removed: bool = False


class Mention(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    app: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    id: str = Field(min_length=1, max_length=100)
    note_id: str = Field(min_length=1, max_length=64)
    note_title: str = Field(min_length=1, max_length=200)
    note_href: str = Field(pattern=r"^/[^/]", max_length=500)
    line: str = Field(default="", max_length=500)
    removed: bool = False


def linkable(**fields: Any) -> dict[str, Any]:
    return _check(Linkable, fields)


PROPERTY_NAME = r"^[a-z][a-z0-9_]{0,39}$"
RESERVED_PROPERTIES = frozenset({"arga", "tipo"})
Property = str | int | float | bool | None | list[str | int | float]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=160, pattern=r"^\S+$")
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=40)
    href: str = Field(pattern=r"^/[^/]", max_length=500)
    folder: str = Field(default="", max_length=300)
    day: date | None = None
    properties: dict[str, Property] = Field(default_factory=dict, max_length=40)
    body: str = Field(default="", max_length=100_000)
    removed: bool = False

    @model_validator(mode="after")
    def _well_formed(self) -> Record:
        for name, value in self.properties.items():
            if not re.fullmatch(PROPERTY_NAME, name):
                raise ValueError(f"properties.{name}: lowercase ASCII letters, digits and _")
            if name in RESERVED_PROPERTIES:
                raise ValueError(f"properties.{name}: set by whoever writes the note")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"properties.{name}: a finite number")
            if isinstance(value, str) and len(value) > 500:
                raise ValueError(f"properties.{name}: longer than 500 characters")
            if isinstance(value, list) and len(value) > 50:
                raise ValueError(f"properties.{name}: more than 50 values")
        parts = self.folder.split("/") if self.folder else []
        if any(not part.strip() or part.strip() in (".", "..") for part in parts):
            raise ValueError("folder: a path without extra slashes or `..`")
        if "%% arga %%" in self.body or "%% /arga %%" in self.body:
            raise ValueError("body: without the block markers, the writer adds them")
        return self


def record(**fields: Any) -> dict[str, Any]:
    return _check(Record, fields)


def mention(**fields: Any) -> dict[str, Any]:
    return _check(Mention, fields)


class ShoppingItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=80)
    quantity: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=120)


class ShoppingAdd(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ShoppingItem] = Field(min_length=1, max_length=40)


class ShoppingAdded(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    class Line(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)

        name: str
        already_on_list: bool

    added: list[Line]
    pending: int = Field(ge=0)


def shopping_add(**fields: Any) -> dict[str, Any]:
    return _check(ShoppingAdd, fields)


def shopping_added(**fields: Any) -> dict[str, Any]:
    return _check(ShoppingAdded, fields)


class BooksWant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=10)
    isbn13: str | None = Field(default=None, pattern=r"^97[89][0-9]{10}$")
    note: str | None = Field(default=None, max_length=300)


class BooksWanted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    book_id: str = Field(min_length=1, max_length=100)
    already: bool
    resolved: bool


def books_want(**fields: Any) -> dict[str, Any]:
    return _check(BooksWant, fields)


def books_wanted(**fields: Any) -> dict[str, Any]:
    return _check(BooksWanted, fields)


class AgendaMove(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: str = Field(min_length=3, max_length=200)
    start: datetime | date
    end: datetime | date
    all_day: bool = False

    @model_validator(mode="before")
    @classmethod
    def _dates_follow_all_day(cls, data: Any) -> Any:
        if isinstance(data, dict):
            all_day = bool(data.get("all_day", False))
            for key in ("start", "end"):
                value = data.get(key)
                if isinstance(value, str):
                    try:
                        parsed = (
                            date.fromisoformat(value) if all_day else datetime.fromisoformat(value)
                        )
                    except ValueError as error:
                        raise ValueError(f"{key}: {value!r} does not match all_day") from error
                    data = {**data, key: parsed}
        return data

    @model_validator(mode="after")
    def _coherent(self) -> AgendaMove:
        if self.all_day:
            if type(self.start) is not date or type(self.end) is not date:
                raise ValueError("all day: dates, without a time")
            if self.end <= self.start:
                raise ValueError("all day: the end is exclusive")
        else:
            for value in (self.start, self.end):
                if not isinstance(value, datetime) or value.utcoffset() is None:
                    raise ValueError("with a time: start and end carry a time zone")
            if self.end < self.start:
                raise ValueError("the end cannot be before the start")
        return self

    @property
    def app(self) -> str:
        return self.uid.split(":", 1)[0]


def agenda_move(**fields: Any) -> dict[str, Any]:
    return _check(AgendaMove, fields)


def agenda_moved(item: dict[str, Any]) -> dict[str, Any]:
    try:
        return {AGENDA: arga_agenda.validate(item)}
    except arga_agenda.BadDated as error:
        raise BadContract(str(error)) from None


Nutrients = dict[str, float]


class PantryFood(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    label: str
    source: str
    nutrients: Nutrients
    grams_per_unit: float | None = None
    density_g_ml: float | None = None
    portions: dict[str, float] = {}
    edible_fraction: float | None = None
    nutrients_per: str = Field(default="100g", pattern="^(100g|unit)$")
    unit_name: str | None = None


class PantryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(pattern="^(usda|off)$")
    source_ref: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = None
    category_hint: str = "other"
    nutrients: Nutrients


class PantrySearch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=2, max_length=60)
    limit: int = Field(default=10, ge=1, le=25)
    outside: bool = True
    enough: int = Field(default=1, ge=1, le=25)


class PantryFound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    foods: list[PantryFood]
    candidates: list[PantryCandidate] = []
    failed: list[dict[str, str]] = []


class PantryImport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(pattern="^(usda|off)$")
    source_ref: str = Field(min_length=1, max_length=40)
    alias: str | None = Field(default=None, max_length=60)
    grams_per_unit: float | None = Field(default=None, gt=0, le=5000)


class PantryNutrients(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ids: list[str] = Field(min_length=1, max_length=100)


class PantryFoods(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    foods: list[PantryFood]


class IntakeReplaceFood(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    old_id: str = Field(min_length=36, max_length=36)
    new_id: str = Field(min_length=36, max_length=36)
    old_label: str = Field(min_length=1, max_length=200)
    new_label: str = Field(min_length=1, max_length=200)


class IntakeReplaced(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: int
    entries: int
    days: list[str]


class RecipesSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(default="", max_length=60)
    limit: int = Field(default=10, ge=1, le=50)


class RecipeRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    servings: int = Field(ge=1)


class RecipesFound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipes: list[RecipeRef]


class RecipeIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    food_id: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0, le=100_000)
    unit: Literal["g", "ml", "unit"] = "g"
    portion: str | None = Field(default=None, min_length=1, max_length=40)


class RecipesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=120)
    servings: int = Field(default=1, ge=1, le=50)
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=60)


class RecipeCreated(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_id: str
    version_id: str


class RecipesNutrientsAsk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)


class RecipeNutrients(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    version_id: str
    version: int = Field(ge=1)
    servings: int = Field(ge=1)
    per_serving: Nutrients
    grams_per_serving: float = Field(ge=0)
    missing: list[str] = []
    coverage: dict[str, float] = {}


def pantry_found(**fields: Any) -> dict[str, Any]:
    return _check(PantryFound, fields)


def pantry_food(**fields: Any) -> dict[str, Any]:
    return _check(PantryFood, fields)


def pantry_foods(**fields: Any) -> dict[str, Any]:
    return _check(PantryFoods, fields)


def intake_replace_food(**fields: Any) -> dict[str, Any]:
    return _check(IntakeReplaceFood, fields)


def intake_replaced(**fields: Any) -> dict[str, Any]:
    return _check(IntakeReplaced, fields)


def recipes_found(**fields: Any) -> dict[str, Any]:
    return _check(RecipesFound, fields)


def recipe_nutrients(**fields: Any) -> dict[str, Any]:
    return _check(RecipeNutrients, fields)


Scalar = str | int | float | bool | None


class NoteRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    folder: str
    title: str
    path: str
    properties: dict[str, Any]
    excerpt: str
    words: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    updated_by: str


class NoteFull(NoteRef):
    body: str
    version: int = Field(ge=1)


class NotesList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    folder: str | None = Field(default=None, max_length=1000)
    property: str | None = Field(default=None, max_length=200)
    value: Scalar = None
    query: str | None = Field(default=None, max_length=300)
    limit: int = Field(default=200, ge=1, le=500)


class NotesFound(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    notes: list[NoteRef]


class NotesRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)


class NotesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    folder: str = Field(max_length=1000)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=500_000)
    properties: dict[str, Scalar] = Field(default_factory=dict)


class NotesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)
    body: str | None = Field(default=None, max_length=500_000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    folder: str | None = Field(default=None, max_length=1000)
    version: int | None = Field(default=None, ge=1)


class NotesTrash(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)


def note_full(**fields: Any) -> dict[str, Any]:
    return _check(NoteFull, fields)


def notes_found(**fields: Any) -> dict[str, Any]:
    return _check(NotesFound, fields)


__all__ = [
    "intake_replaced",
    "intake_replace_food",
    "IntakeReplaced",
    "IntakeReplaceFood",
    "INTAKE_REPLACE_FOOD",
    "PANTRY",
    "PANTRY_IMPORT",
    "PANTRY_NUTRIENTS",
    "PANTRY_SEARCH",
    "RECIPES_CREATE",
    "RECIPES_NUTRIENTS",
    "RECIPES_SEARCH",
    "RecipeCreated",
    "RecipeIngredient",
    "RecipesCreate",
    "PantryCandidate",
    "PantryFood",
    "PantryFound",
    "PantryFoods",
    "PantryImport",
    "PantryNutrients",
    "PantrySearch",
    "RecipeNutrients",
    "RecipeRef",
    "RecipesFound",
    "RecipesNutrientsAsk",
    "RecipesSearch",
    "pantry_food",
    "pantry_foods",
    "pantry_found",
    "recipe_nutrients",
    "recipes_found",
    "METRIC",
    "Metric",
    "UNITS",
    "metric",
    "metric_identity",
    "ADDRESSED",
    "AGENDA",
    "AGENDA_MOVE",
    "AgendaMove",
    "agenda_move",
    "agenda_moved",
    "NOTES",
    "NOTES_CREATE",
    "NOTES_LIST",
    "NOTES_READ",
    "NOTES_TRASH",
    "NOTES_WRITE",
    "NoteFull",
    "NoteRef",
    "NotesCreate",
    "NotesFound",
    "NotesList",
    "NotesRead",
    "NotesTrash",
    "NotesWrite",
    "note_full",
    "notes_found",
    "ACTIVITY",
    "BODY_WEIGHT",
    "LINKABLE",
    "MENTION",
    "RECORD",
    "Record",
    "record",
    "Linkable",
    "Mention",
    "linkable",
    "mention",
    "CONTRACTS",
    "SERVICES",
    "SHOPPING_ADD",
    "BadContract",
    "BodyWeight",
    "ShoppingAdd",
    "ShoppingAdded",
    "ShoppingItem",
    "activity",
    "body_weight",
    "shopping_add",
    "shopping_added",
]
