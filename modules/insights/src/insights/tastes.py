from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from insights.words import say

Facet = Literal[
    "topic", "genre", "format", "creator", "work", "style", "avoid", "context", "language"
]
TraitSource = Literal["said", "answered", "seen", "rated"]
Status = Literal["proposed", "confirmed", "rejected"]
QuestionKind = Literal["one", "many", "scale", "either", "confirm", "free"]
Rhythm = Literal["never", "sometimes", "daily"]
SourceKind = Literal["magazine", "blog", "podcast", "video", "forum", "media", "reference"]

FACETS: dict[str, str] = {
    "topic": "Topics",
    "genre": "Genres",
    "format": "Formats",
    "creator": "Authors and creators",
    "work": "Works that marked them",
    "style": "How they like to be told things",
    "avoid": "What they do not want to hear about",
    "context": "What they are living now",
    "language": "Languages",
}

GLYPHS = frozenset(
    {
        "landmark",
        "globe",
        "atom",
        "chip",
        "wallet",
        "book",
        "mountain",
        "image",
        "spark",
        "compass",
        "music",
        "food",
        "heart",
        "flame",
        "graph",
        "layers",
        "plane",
        "target",
        "bolt",
        "people",
        "castle",
        "film",
        "headphones",
        "lightbulb",
    }
)

RHYTHM_DAYS = {"sometimes": 3, "daily": 1}
TOPIC_QUIET = timedelta(days=60)


class NotFound(Exception):
    pass


class Refused(Exception):
    pass


def key_of(label: str) -> str:
    plain = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    plain = re.sub(r"[^a-z0-9 _.:-]+", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return (plain or "x")[:120]


class Settings(BaseModel):
    pill_on: bool = True
    pill_time: str = "09:00"
    pill_minutes: Literal[5, 10, 15, 20, 30] = 15
    pill_language: str | None = None
    pill_level: Literal["A1", "A2", "B1", "B2", "C1", "C2"] | None = None
    questions: Rhythm = "sometimes"
    started_at: datetime | None = None


class SettingsIn(BaseModel):
    pill_on: bool | None = None
    pill_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    pill_minutes: Literal[5, 10, 15, 20, 30] | None = None
    pill_language: str | None = Field(default=None, pattern=r"^([a-z]{2}|none)$")
    pill_level: Literal["A1", "A2", "B1", "B2", "C1", "C2"] | None = None
    questions: Rhythm | None = None


SETTINGS = text("""
    select pill_on, pill_time, pill_minutes, pill_language, pill_level, questions, started_at
    from insights.insights_profile
""")


async def settings(connection: AsyncConnection) -> Settings:
    row = (await connection.execute(SETTINGS)).first()
    if row is None:
        return Settings()
    return Settings(
        pill_on=row.pill_on,
        pill_time=row.pill_time.strftime("%H:%M"),
        pill_minutes=row.pill_minutes,
        pill_language=row.pill_language,
        pill_level=row.pill_level,
        questions=row.questions,
        started_at=row.started_at,
    )


async def _ensure_profile(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            "insert into insights.insights_profile (about) values ('') on conflict (user_id) do nothing"
        )
    )


async def save_settings(connection: AsyncConnection, wanted: SettingsIn) -> Settings:
    await _ensure_profile(connection)
    changes = wanted.model_dump(exclude_unset=True)
    if "pill_language" in changes and changes["pill_language"] == "none":
        changes["pill_language"] = None
    if "pill_time" in changes and changes["pill_time"] is not None:
        hours, minutes = changes["pill_time"].split(":")
        changes["pill_time"] = time(int(hours), int(minutes))
    allowed = ("pill_on", "pill_time", "pill_minutes", "pill_language", "pill_level", "questions")
    sets = [f"{name} = :{name}" for name in allowed if name in changes]
    if sets:
        await connection.execute(
            text(f"update insights.insights_profile set {', '.join(sets)}, updated_at = now()"),
            {name: changes[name] for name in allowed if name in changes},
        )
    return await settings(connection)


async def mark_started(connection: AsyncConnection) -> None:
    await _ensure_profile(connection)
    await connection.execute(
        text("update insights.insights_profile set started_at = coalesce(started_at, now())")
    )


@dataclass(frozen=True)
class SourceSeed:
    name: str
    kind: str
    language: str
    url: str


@dataclass(frozen=True)
class FamilySeed:
    key: str
    hue: int
    glyph: str
    sources: tuple[SourceSeed, ...] = ()
    outside: bool = False

    @property
    def name(self) -> str:
        return say(f"family.{self.key}.name")

    @property
    def themes(self) -> str:
        return say(f"family.{self.key}.themes")


def _s(name: str, kind: str, language: str, url: str) -> SourceSeed:
    return SourceSeed(name, kind, language, url)


FAMILIES: tuple[FamilySeed, ...] = (
    FamilySeed(
        "history",
        3,
        "landmark",
        (
            _s("Desperta Ferro", "magazine", "es", "https://www.despertaferro-ediciones.com"),
            _s(
                "National Geographic Historia",
                "magazine",
                "es",
                "https://historia.nationalgeographic.com.es",
            ),
            _s("World History Encyclopedia", "reference", "es", "https://www.worldhistory.org"),
            _s("SER Historia", "podcast", "es", "https://cadenaser.com/podcast/ser-historia/"),
            _s(
                "The Rest Is History",
                "podcast",
                "en",
                "https://www.goalhanger.com/the-rest-is-history/",
            ),
            _s("Fall of Civilizations", "podcast", "en", "https://fallofcivilizationspodcast.com"),
            _s("r/AskHistorians", "forum", "en", "https://www.reddit.com/r/AskHistorians/"),
        ),
    ),
    FamilySeed(
        "geopolitics",
        1,
        "globe",
        (
            _s("El Orden Mundial", "media", "es", "https://elordenmundial.com"),
            _s("Pol\u00edtica Exterior", "magazine", "es", "https://www.politicaexterior.com"),
            _s("CIDOB", "reference", "es", "https://www.cidob.org"),
            _s("Foreign Affairs", "magazine", "en", "https://www.foreignaffairs.com"),
            _s("International Crisis Group", "reference", "en", "https://www.crisisgroup.org"),
            _s("Caspian Report", "video", "en", "https://www.youtube.com/@CaspianReport"),
        ),
    ),
    FamilySeed(
        "science",
        5,
        "atom",
        (
            _s("Quanta Magazine", "magazine", "en", "https://www.quantamagazine.org"),
            _s("Naukas", "blog", "es", "https://naukas.com"),
            _s(
                "Cuaderno de Cultura Cient\u00edfica", "blog", "es", "https://culturacientifica.com"
            ),
            _s("QuantumFracture", "video", "es", "https://www.youtube.com/@QuantumFracture"),
            _s(
                "Coffee Break: Se\u00f1al y Ruido",
                "podcast",
                "es",
                "https://www.ivoox.com/podcast-coffee-break-senal-ruido_sq_f1172179_1.html",
            ),
            _s("r/askscience", "forum", "en", "https://www.reddit.com/r/askscience/"),
        ),
    ),
    FamilySeed(
        "technology",
        6,
        "chip",
        (
            _s("Ars Technica", "media", "en", "https://arstechnica.com"),
            _s("IEEE Spectrum", "magazine", "en", "https://spectrum.ieee.org"),
            _s("Xataka", "media", "es", "https://www.xataka.com"),
            _s("Computerphile", "video", "en", "https://www.youtube.com/@Computerphile"),
            _s("Acquired", "podcast", "en", "https://www.acquired.fm"),
        ),
    ),
    FamilySeed(
        "economy",
        2,
        "wallet",
        (
            _s("Nada es Gratis", "blog", "es", "https://nadaesgratis.es"),
            _s("The Economist", "magazine", "en", "https://www.economist.com"),
            _s("Planet Money", "podcast", "en", "https://www.npr.org/podcasts/510289/planet-money"),
            _s("Freakonomics Radio", "podcast", "en", "https://freakonomics.com"),
            _s("Our World in Data", "reference", "en", "https://ourworldindata.org"),
        ),
    ),
    FamilySeed(
        "ideas",
        8,
        "book",
        (
            _s(
                "Stanford Encyclopedia of Philosophy",
                "reference",
                "en",
                "https://plato.stanford.edu",
            ),
            _s("Aeon", "magazine", "en", "https://aeon.co"),
            _s("Filosof\u00eda&co", "magazine", "es", "https://www.filco.es"),
            _s("Philosophize This!", "podcast", "en", "https://www.philosophizethis.org"),
        ),
    ),
    FamilySeed(
        "nature",
        2,
        "mountain",
        (
            _s(
                "National Geographic Espa\u00f1a",
                "magazine",
                "es",
                "https://www.nationalgeographic.com.es",
            ),
            _s("Kurzgesagt", "video", "es", "https://www.youtube.com/@KurzgesagtES"),
            _s("iNaturalist", "reference", "es", "https://www.inaturalist.org"),
        ),
    ),
    FamilySeed(
        "culture",
        7,
        "image",
        (
            _s("Jot Down", "magazine", "es", "https://www.jotdown.es"),
            _s("The Public Domain Review", "magazine", "en", "https://publicdomainreview.org"),
            _s("99% Invisible", "podcast", "en", "https://99percentinvisible.org"),
            _s("Smarthistory", "video", "en", "https://smarthistory.org"),
        ),
    ),
    FamilySeed(
        "curiosities",
        3,
        "spark",
        (
            _s("Atlas Obscura", "magazine", "en", "https://www.atlasobscura.com"),
            _s("Damn Interesting", "blog", "en", "https://www.damninteresting.com"),
            _s("Today I Found Out", "blog", "en", "https://www.todayifoundout.com"),
            _s("Muy Interesante", "magazine", "es", "https://www.muyinteresante.com"),
        ),
    ),
    FamilySeed(
        "outside",
        4,
        "compass",
        (
            _s("99% Invisible", "podcast", "en", "https://99percentinvisible.org"),
            _s("Radiolab", "podcast", "en", "https://radiolab.org"),
            _s("Atlas Obscura", "magazine", "en", "https://www.atlasobscura.com"),
        ),
        outside=True,
    ),
)


class Family(BaseModel):
    key: str
    name: str
    hue: int
    glyph: str
    themes: str
    weight: int
    outside: bool


class FamilyIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    themes: str = Field(default="", max_length=500)
    glyph: str = "spark"
    hue: int = Field(default=3, ge=1, le=8)
    weight: int = Field(default=2, ge=0, le=3)

    @field_validator("glyph")
    @classmethod
    def _known_glyph(cls, value: str) -> str:
        if value not in GLYPHS:
            raise ValueError(f"glyph: one of {sorted(GLYPHS)}")
        return value


class FamilyChange(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    themes: str | None = Field(default=None, max_length=500)
    weight: int | None = Field(default=None, ge=0, le=3)


class Source(BaseModel):
    id: str
    family_key: str
    name: str
    kind: SourceKind
    language: str
    url: str
    builtin: bool
    hidden: bool


class SourceIn(BaseModel):
    family_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,30}$")
    name: str = Field(min_length=1, max_length=80)
    kind: SourceKind = "magazine"
    language: str = Field(default="es", pattern=r"^[a-z]{2}$")
    url: str = Field(pattern=r"^https://[^\s]{3,300}$")


class SourceChange(BaseModel):
    hidden: bool


FAMILY_COLUMNS = "key, name, hue, glyph, themes, weight, outside"
SOURCE_COLUMNS = "id::text as id, family_key, name, kind, language, url, builtin, hidden"


def default_families() -> list[Family]:
    return [
        Family(
            key=one.key,
            name=one.name,
            hue=one.hue,
            glyph=one.glyph,
            themes=one.themes,
            weight=1,
            outside=one.outside,
        )
        for one in FAMILIES
    ]


async def ensure_defaults(connection: AsyncConnection) -> None:
    have = await connection.scalar(text("select count(*) from insights.insights_family"))
    if have:
        return
    for position, one in enumerate(FAMILIES):
        await connection.execute(
            text("""
                insert into insights.insights_family
                    (key, name, hue, glyph, themes, weight, outside, position)
                values (:key, :name, :hue, :glyph, :themes, 1, :outside, :position)
                on conflict (user_id, key) do nothing
            """),
            {
                "key": one.key,
                "name": one.name,
                "hue": one.hue,
                "glyph": one.glyph,
                "themes": one.themes,
                "outside": one.outside,
                "position": position,
            },
        )
        for source in one.sources:
            await connection.execute(
                text("""
                    insert into insights.insights_source (family_key, name, kind, language, url, builtin)
                    values (:family, :name, :kind, :language, :url, true)
                    on conflict (user_id, family_key, name) do nothing
                """),
                {"family": one.key, **source.__dict__},
            )


async def families(connection: AsyncConnection) -> list[Family]:
    rows = (
        await connection.execute(
            text(
                f"select {FAMILY_COLUMNS} from insights.insights_family order by position, created_at"
            )
        )
    ).all()
    if not rows:
        return default_families()
    return [Family.model_validate(dict(row._mapping)) for row in rows]


async def change_family(connection: AsyncConnection, key: str, wanted: FamilyChange) -> Family:
    await ensure_defaults(connection)
    changes = wanted.model_dump(exclude_unset=True, exclude_none=True)
    if changes:
        sets = ", ".join(f"{name} = :{name}" for name in changes)
        done = await connection.execute(
            text(f"update insights.insights_family set {sets} where key = :key"),
            {**changes, "key": key},
        )
        if done.rowcount == 0:
            raise NotFound(key)
    found = next((one for one in await families(connection) if one.key == key), None)
    if found is None:
        raise NotFound(key)
    return found


async def add_family(connection: AsyncConnection, wanted: FamilyIn) -> Family:
    await ensure_defaults(connection)
    base = re.sub(r"[^a-z0-9]+", "_", key_of(wanted.name)).strip("_")[:24] or "tema"
    if not base[0].isalpha():
        base = f"t_{base}"[:24]
    taken = {one.key for one in await families(connection)}
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    position = await connection.scalar(
        text("select coalesce(max(position), 0) + 1 from insights.insights_family")
    )
    await connection.execute(
        text("""
            insert into insights.insights_family (key, name, hue, glyph, themes, weight, position)
            values (:key, :name, :hue, :glyph, :themes, :weight, :position)
        """),
        {**wanted.model_dump(), "key": key, "position": position},
    )
    return next(one for one in await families(connection) if one.key == key)


def default_sources() -> list[Source]:
    return [
        Source(
            id=f"builtin:{family.key}:{key_of(one.name)}",
            family_key=family.key,
            name=one.name,
            kind=one.kind,  # type: ignore[arg-type]
            language=one.language,
            url=one.url,
            builtin=True,
            hidden=False,
        )
        for family in FAMILIES
        for one in family.sources
    ]


async def sources(connection: AsyncConnection) -> list[Source]:
    rows = (
        await connection.execute(
            text(
                f"select {SOURCE_COLUMNS} from insights.insights_source order by family_key, created_at"
            )
        )
    ).all()
    if not rows and not await connection.scalar(
        text("select count(*) from insights.insights_family")
    ):
        return default_sources()
    return [Source.model_validate(dict(row._mapping)) for row in rows]


async def add_source(connection: AsyncConnection, wanted: SourceIn) -> Source:
    await ensure_defaults(connection)
    if wanted.family_key not in {one.key for one in await families(connection)}:
        raise NotFound(wanted.family_key)
    row = (
        await connection.execute(
            text(f"""
                insert into insights.insights_source (family_key, name, kind, language, url)
                values (:family_key, :name, :kind, :language, :url)
                on conflict (user_id, family_key, name) do update
                set url = excluded.url, kind = excluded.kind, language = excluded.language,
                    hidden = false
                returning {SOURCE_COLUMNS}
            """),
            wanted.model_dump(),
        )
    ).one()
    return Source.model_validate(dict(row._mapping))


async def change_source(
    connection: AsyncConnection, source_id: str, wanted: SourceChange
) -> Source:
    row = (
        await connection.execute(
            text(f"""
                update insights.insights_source set hidden = :hidden where id = cast(:id as uuid)
                returning {SOURCE_COLUMNS}
            """),
            {"id": source_id, "hidden": wanted.hidden},
        )
    ).first()
    if row is None:
        raise NotFound(source_id)
    return Source.model_validate(dict(row._mapping))


class Trait(BaseModel):
    id: str
    facet: Facet
    label: str
    stance: int
    source: TraitSource
    evidence: str | None
    status: Status
    updated_at: datetime


class TraitIn(BaseModel):
    facet: Facet
    label: str = Field(min_length=1, max_length=120)
    stance: int = Field(default=1, ge=-2, le=2)


class TraitChange(BaseModel):
    status: Status | None = None
    stance: int | None = Field(default=None, ge=-2, le=2)
    label: str | None = Field(default=None, min_length=1, max_length=120)


TRAIT_COLUMNS = "id::text as id, facet, label, stance, source, evidence, status, updated_at"


def _trait(row: Any) -> Trait:
    return Trait.model_validate(dict(row._mapping))


async def traits(connection: AsyncConnection, *, include_rejected: bool = True) -> list[Trait]:
    rows = await connection.execute(
        text(f"""
            select {TRAIT_COLUMNS} from insights.insights_trait
            where :rejected or status <> 'rejected'
            order by case status when 'proposed' then 0 when 'confirmed' then 1 else 2 end,
                     abs(stance) desc, updated_at desc
        """),
        {"rejected": include_rejected},
    )
    return [_trait(row) for row in rows]


async def one_trait(connection: AsyncConnection, trait_id: str) -> Trait:
    row = (
        await connection.execute(
            text(
                f"select {TRAIT_COLUMNS} from insights.insights_trait where id = cast(:id as uuid)"
            ),
            {"id": trait_id},
        )
    ).first()
    if row is None:
        raise NotFound(trait_id)
    return _trait(row)


async def remember(
    connection: AsyncConnection,
    facet: str,
    label: str,
    stance: int,
    source: str,
    *,
    evidence: str | None = None,
    confirmed: bool,
) -> tuple[Trait, str]:
    key = key_of(label)
    row = (
        await connection.execute(
            text(f"""
                select {TRAIT_COLUMNS} from insights.insights_trait where facet = :facet and key = :key
            """),
            {"facet": facet, "key": key},
        )
    ).first()
    if row is not None:
        found = _trait(row)
        if not confirmed and found.status == "rejected":
            return found, "rejected"
        if not confirmed and found.status == "confirmed":
            if evidence:
                await connection.execute(
                    text("""
                        update insights.insights_trait set evidence = :evidence, updated_at = now()
                        where id = cast(:id as uuid)
                    """),
                    {"evidence": evidence[:300], "id": found.id},
                )
            return await one_trait(connection, found.id), "kept"
        await connection.execute(
            text("""
                update insights.insights_trait
                set label = :label, stance = :stance, source = :source,
                    evidence = coalesce(:evidence, evidence), status = :status, updated_at = now()
                where id = cast(:id as uuid)
            """),
            {
                "label": label.strip()[:120],
                "stance": stance,
                "source": source,
                "evidence": evidence[:300] if evidence else None,
                "status": "confirmed" if confirmed else "proposed",
                "id": found.id,
            },
        )
        return await one_trait(connection, found.id), "updated"
    created = (
        await connection.execute(
            text(f"""
                insert into insights.insights_trait (facet, key, label, stance, source, evidence, status)
                values (:facet, :key, :label, :stance, :source, :evidence, :status)
                returning {TRAIT_COLUMNS}
            """),
            {
                "facet": facet,
                "key": key,
                "label": label.strip()[:120],
                "stance": stance,
                "source": source,
                "evidence": evidence[:300] if evidence else None,
                "status": "confirmed" if confirmed else "proposed",
            },
        )
    ).one()
    return _trait(created), "new"


async def add_trait(connection: AsyncConnection, wanted: TraitIn) -> Trait:
    found, _ = await remember(
        connection, wanted.facet, wanted.label, wanted.stance, "said", confirmed=True
    )
    return found


async def change_trait(connection: AsyncConnection, trait_id: str, wanted: TraitChange) -> Trait:
    changes = wanted.model_dump(exclude_unset=True, exclude_none=True)
    if "label" in changes:
        changes["key"] = key_of(changes["label"])
    if changes:
        sets = ", ".join(f"{name} = :{name}" for name in changes)
        done = await connection.execute(
            text(f"""
                update insights.insights_trait set {sets}, updated_at = now() where id = cast(:id as uuid)
            """),
            {**changes, "id": trait_id},
        )
        if done.rowcount == 0:
            raise NotFound(trait_id)
    return await one_trait(connection, trait_id)


async def forget_trait(connection: AsyncConnection, trait_id: str) -> None:
    await connection.execute(
        text("delete from insights.insights_trait where id = cast(:id as uuid)"), {"id": trait_id}
    )


class Option(BaseModel):
    value: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=80)


class Question(BaseModel):
    id: str | None
    origin: Literal["start", "pass"]
    bank_key: str | None
    kind: QuestionKind
    text: str
    why: str | None
    options: list[Option]
    topic: str | None = None
    trait_id: str | None = None
    asked_at: datetime | None = None
    answer: dict[str, Any] | None = None
    answered_at: datetime | None = None
    skipped_at: datetime | None = None


class Answer(BaseModel):
    values: list[str] = Field(default_factory=list, max_length=20)
    text: str | None = Field(default=None, max_length=1000)
    value: str | None = Field(default=None, max_length=60)


@dataclass(frozen=True)
class Asked:
    key: str
    kind: str
    options: tuple[str, ...] = ()
    families: bool = False
    when: tuple[str, str] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return say(f"{self.key}.text")

    @property
    def why(self) -> str:
        return say(f"{self.key}.why")

    def label(self, value: str) -> str:
        return say(f"{self.key}.option.{value}")


BANK: tuple[Asked, ...] = (
    Asked("start.families", "many", families=True),
    Asked("start.favourite", "one", families=True),
    Asked("start.depth", "one", ("clear", "deep", "mixed")),
    Asked("start.formats", "many", ("read", "listen", "watch", "screen")),
    Asked("start.fiction", "many", ("fantasy", "scifi", "historical", "crime", "literary", "none")),
    Asked("start.loved", "free"),
    Asked("start.minutes", "one", ("5", "10", "15", "20", "30")),
    Asked("start.time", "one", ("07:30", "09:00", "13:30", "18:00", "21:30")),
    Asked("start.languages", "many", ("es", "en", "de", "fr", "eu", "it")),
    Asked("start.learning", "one", ("none", "de", "en", "fr", "it")),
    Asked("start.level", "one", ("A2", "B1", "B2", "C1"), when=("start.learning", "!none")),
    Asked("start.outside", "one", ("often", "sometimes", "never")),
    Asked("start.avoid", "free"),
)
BANK_BY_KEY = {one.key: one for one in BANK}

FORMATS = ("read", "listen", "watch", "screen")
DEPTH = ("clear", "deep", "mixed")
FICTION = ("fantasy", "scifi", "historical", "crime", "literary")
LANGUAGES = ("es", "en", "de", "fr", "eu", "it")


def _said(kind: str, value: str) -> str:
    return say(f"taste.{kind}.{value}")


OUTSIDE_WEIGHT = {"often": 2, "sometimes": 1, "never": 0}

QUESTION_COLUMNS = (
    "id::text as id, origin, bank_key, kind, text, why, options, topic, "
    "trait_id::text as trait_id, "
    "asked_at, answer, answered_at, skipped_at"
)


def _question(row: Any) -> Question:
    return Question.model_validate(dict(row._mapping))


def _bank_question(asked: Asked, family_list: list[Family]) -> Question:
    options = (
        [Option(value=one.key, label=one.name) for one in family_list]
        if asked.families
        else [Option(value=value, label=asked.label(value)) for value in asked.options]
    )
    return Question(
        id=None,
        origin="start",
        bank_key=asked.key,
        kind=asked.kind,  # type: ignore[arg-type]
        text=asked.text,
        why=asked.why,
        options=options,
    )


async def _bank_answers(connection: AsyncConnection) -> dict[str, Question]:
    rows = await connection.execute(
        text(f"select {QUESTION_COLUMNS} from insights.insights_question where origin = 'start'")
    )
    return {row.bank_key: _question(row) for row in rows if row.bank_key}


def _applies(asked: Asked, done: dict[str, Question]) -> bool:
    if asked.when is None:
        return True
    other, wanted = asked.when
    answer = done.get(other)
    if answer is None or answer.answer is None:
        return False
    chosen = (answer.answer.get("values") or [None])[0]
    if wanted.startswith("!"):
        return chosen is not None and chosen != wanted[1:]
    return chosen == wanted


class Onboarding(BaseModel):
    done: bool
    answered: int
    total: int
    questions: list[Question]


async def onboarding(connection: AsyncConnection) -> Onboarding:
    done = await _bank_answers(connection)
    family_list = [one for one in await families(connection) if not one.outside]
    favourite_from = done.get("start.families")
    pending: list[Question] = []
    applicable = [one for one in BANK if _applies(one, done)]
    for asked in applicable:
        if asked.key in done:
            continue
        question = _bank_question(asked, family_list)
        if asked.key == "start.favourite" and favourite_from and favourite_from.answer:
            chosen = set(favourite_from.answer.get("values") or [])
            if chosen:
                question.options = [one for one in question.options if one.value in chosen]
        pending.append(question)
    answered = sum(1 for one in applicable if one.key in done)
    return Onboarding(done=not pending, answered=answered, total=len(applicable), questions=pending)


def _items(free: str | None) -> list[str]:
    if not free:
        return []
    parts = re.split(r"[\n,;]+", free)
    return [part.strip(" .-·•\t")[:120] for part in parts if part.strip(" .-·•\t")][:12]


async def _weight(connection: AsyncConnection, key: str, weight: int, *, at_least: bool) -> None:
    clause = "greatest(weight, :weight)" if at_least else ":weight"
    await connection.execute(
        text(f"update insights.insights_family set weight = {clause} where key = :key"),
        {"key": key, "weight": weight},
    )


async def _apply(connection: AsyncConnection, key: str, answer: Answer) -> None:
    chosen = answer.values
    names = {one.key: one.name for one in await families(connection)}
    if key == "start.families":
        for family in chosen:
            if family in names:
                await _weight(connection, family, 2, at_least=True)
                await remember(connection, "topic", names[family], 1, "answered", confirmed=True)
    elif key == "start.favourite":
        for family in chosen[:1]:
            if family in names:
                await _weight(connection, family, 3, at_least=False)
                await remember(connection, "topic", names[family], 2, "answered", confirmed=True)
    elif key == "start.depth":
        for value in chosen[:1]:
            if value in DEPTH:
                await remember(
                    connection, "style", _said("depth", value), 1, "answered", confirmed=True
                )
    elif key == "start.formats":
        for value in chosen:
            if value in FORMATS:
                await remember(
                    connection, "format", _said("format", value), 1, "answered", confirmed=True
                )
    elif key == "start.fiction":
        if "none" in chosen:
            await remember(
                connection, "genre", _said("fiction", "all"), -1, "answered", confirmed=True
            )
        for value in chosen:
            if value in FICTION:
                await remember(
                    connection, "genre", _said("fiction", value), 1, "answered", confirmed=True
                )
    elif key == "start.loved":
        for item in _items(answer.text):
            await remember(connection, "work", item, 2, "said", confirmed=True)
    elif key == "start.avoid":
        for item in _items(answer.text):
            await remember(connection, "avoid", item, -2, "said", confirmed=True)
    elif key == "start.languages":
        for value in chosen:
            if value in LANGUAGES:
                await remember(
                    connection, "language", _said("language", value), 1, "answered", confirmed=True
                )
    elif key == "start.minutes" and chosen:
        await save_settings(connection, SettingsIn(pill_minutes=int(chosen[0])))  # type: ignore[arg-type]
    elif key == "start.time" and chosen:
        await save_settings(connection, SettingsIn(pill_time=chosen[0]))
    elif key == "start.learning" and chosen:
        await save_settings(connection, SettingsIn(pill_language=chosen[0]))
    elif key == "start.level" and chosen:
        await save_settings(connection, SettingsIn(pill_level=chosen[0]))  # type: ignore[arg-type]
    elif key == "start.outside" and chosen:
        await connection.execute(
            text("update insights.insights_family set weight = :weight where outside"),
            {"weight": OUTSIDE_WEIGHT.get(chosen[0], 1)},
        )


async def answer_start(
    connection: AsyncConnection, bank_key: str, answer: Answer | None
) -> Onboarding:
    asked = BANK_BY_KEY.get(bank_key)
    if asked is None:
        raise NotFound(bank_key)
    await ensure_defaults(connection)
    await mark_started(connection)
    family_list = await families(connection)
    question = _bank_question(asked, family_list)
    valid = {one.value for one in question.options}
    if answer is not None and asked.kind in ("one", "many"):
        answer = Answer(values=[one for one in answer.values if one in valid])
        if asked.kind == "one":
            answer = Answer(values=answer.values[:1])
    await connection.execute(
        text("""
            insert into insights.insights_question
                (origin, bank_key, kind, text, why, options, answer, answered_at, skipped_at)
            values ('start', :key, :kind, :text, :why, cast(:options as jsonb),
                    cast(:answer as jsonb),
                    case when cast(:answer as jsonb) is null then null else now() end,
                    case when cast(:answer as jsonb) is null then now() else null end)
            on conflict (user_id, bank_key) where bank_key is not null do update
            set answer = excluded.answer, answered_at = excluded.answered_at,
                skipped_at = excluded.skipped_at
        """),
        {
            "key": bank_key,
            "kind": asked.kind,
            "text": asked.text,
            "why": asked.why,
            "options": json.dumps([one.model_dump() for one in question.options]),
            "answer": json.dumps(answer.model_dump()) if answer is not None else None,
        },
    )
    if answer is not None:
        await _apply(connection, bank_key, answer)
    return await onboarding(connection)


class QuestionIn(BaseModel):
    kind: QuestionKind = Field(
        description=(
            "`one` choose one, `many` several, `either` between two, `scale` from 1 to 5, "
            "`confirm` yes or no to a proposed trait (with `trait_id`), `free` free text. Better "
            "those answered with one tap."
        )
    )
    text: str = Field(min_length=3, max_length=200, description="The question, informal and short.")
    why: str = Field(
        min_length=5,
        max_length=200,
        description="Why you ask, in one sentence: `You finished a novel you rated 5`.",
    )
    options: list[Option] = Field(
        default_factory=list,
        max_length=8,
        description="For `one`, `many` and `either`: 2 to 8 options. Empty in the others.",
    )
    topic: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._:-]{1,79}$",
        description=(
            "What it is about, to avoid asking it again: `library.finished:a-novel-title`, "
            "`taste.reading-pace`."
        ),
    )
    trait_id: str | None = Field(
        default=None, description="Only in `confirm`: the proposed trait you want to confirm."
    )


async def current_question(connection: AsyncConnection) -> Question | None:
    row = (
        await connection.execute(
            text(f"""
                select {QUESTION_COLUMNS} from insights.insights_question
                where origin = 'pass' and answered_at is null and skipped_at is null
                order by asked_at limit 1
            """)
        )
    ).first()
    return _question(row) if row else None


async def ask(connection: AsyncConnection, wanted: QuestionIn, now: datetime) -> Question:
    rhythm = (await settings(connection)).questions
    if rhythm == "never":
        raise Refused("the person does not want questions: their rhythm is `never`")
    if wanted.kind in ("one", "many", "either") and len(wanted.options) < 2:
        raise Refused("a choice question needs at least two options")
    if wanted.kind == "either" and len(wanted.options) != 2:
        raise Refused("`either` is between exactly two options")
    if wanted.kind == "confirm":
        if not wanted.trait_id:
            raise Refused("`confirm` needs the `trait_id` of the proposed trait")
        await one_trait(connection, wanted.trait_id)
    if await current_question(connection) is not None:
        raise Refused("a question is already waiting for an answer: do not leave another")
    last = await connection.scalar(
        text("select max(asked_at) from insights.insights_question where origin = 'pass'")
    )
    gap = timedelta(days=RHYTHM_DAYS[rhythm])
    if last is not None and now - last < gap - timedelta(hours=2):
        raise Refused(f"with their rhythm (`{rhythm}`), at most one every {gap.days} day(s)")
    repeated = await connection.scalar(
        text("""
            select count(*) from insights.insights_question
            where origin = 'pass' and topic = :topic and asked_at > :since
        """),
        {"topic": wanted.topic, "since": now - TOPIC_QUIET},
    )
    if repeated:
        raise Refused(f"you asked about `{wanted.topic}` less than 60 days ago")
    options = wanted.options if wanted.kind in ("one", "many", "either") else []
    if wanted.kind == "confirm":
        options = [
            Option(value="yes", label=say("answer.yes")),
            Option(value="no", label=say("answer.no")),
        ]
    if wanted.kind == "scale":
        options = [Option(value=str(n), label=str(n)) for n in range(1, 6)]
    row = (
        await connection.execute(
            text(f"""
                insert into insights.insights_question
                    (origin, kind, text, why, options, topic, trait_id)
                values ('pass', :kind, :text, :why, cast(:options as jsonb), :topic,
                        cast(:trait as uuid))
                returning {QUESTION_COLUMNS}
            """),
            {
                "kind": wanted.kind,
                "text": wanted.text,
                "why": wanted.why,
                "options": json.dumps([one.model_dump() for one in options]),
                "topic": wanted.topic,
                "trait": wanted.trait_id,
            },
        )
    ).one()
    return _question(row)


async def answer_question(
    connection: AsyncConnection, question_id: str, answer: Answer | None
) -> Question:
    row = (
        await connection.execute(
            text(
                f"select {QUESTION_COLUMNS} from insights.insights_question where id = cast(:id as uuid)"
            ),
            {"id": question_id},
        )
    ).first()
    if row is None:
        raise NotFound(question_id)
    question = _question(row)
    await connection.execute(
        text("""
            update insights.insights_question
            set answer = cast(:answer as jsonb),
                answered_at = case when cast(:answer as jsonb) is null then null else now() end,
                skipped_at = case when cast(:answer as jsonb) is null then now() else null end
            where id = cast(:id as uuid)
        """),
        {"id": question_id, "answer": json.dumps(answer.model_dump()) if answer else None},
    )
    if answer is not None and question.kind == "confirm" and question.trait_id:
        said = answer.value or (answer.values[0] if answer.values else None)
        if said in ("yes", "no"):
            await connection.execute(
                text("""
                    update insights.insights_trait set status = :status, updated_at = now()
                    where id = cast(:id as uuid)
                """),
                {"status": "confirmed" if said == "yes" else "rejected", "id": question.trait_id},
            )
    row = (
        await connection.execute(
            text(
                f"select {QUESTION_COLUMNS} from insights.insights_question where id = cast(:id as uuid)"
            ),
            {"id": question_id},
        )
    ).one()
    return _question(row)


async def fresh_answers(connection: AsyncConnection) -> list[Question]:
    rows = await connection.execute(
        text(f"""
            select {QUESTION_COLUMNS} from insights.insights_question
            where origin = 'pass' and answered_at is not null and seen_at is null
            order by answered_at
        """)
    )
    return [_question(row) for row in rows]


async def mark_seen(connection: AsyncConnection, ids: list[str]) -> None:
    if ids:
        await connection.execute(
            text("""
                update insights.insights_question set seen_at = now()
                where id = any(cast(:ids as uuid[]))
            """),
            {"ids": ids},
        )


def said_answer(question: Question) -> str:
    if question.answer is None:
        return "(skipped)"
    labels = {one.value: one.label for one in question.options}
    if question.answer.get("text"):
        return str(question.answer["text"])
    chosen = question.answer.get("values") or (
        [question.answer["value"]] if question.answer.get("value") else []
    )
    return ", ".join(labels.get(one, one) for one in chosen) or "(no answer)"


class Tastes(BaseModel):
    traits: list[Trait]
    families: list[Family]
    sources: list[Source]
    settings: Settings
    onboarding: Onboarding


async def everything(connection: AsyncConnection) -> Tastes:
    return Tastes(
        traits=await traits(connection),
        families=await families(connection),
        sources=await sources(connection),
        settings=await settings(connection),
        onboarding=await onboarding(connection),
    )


def described(found: list[Trait]) -> list[str]:
    lines = []
    for one in found:
        if one.status == "rejected":
            continue
        mark = "" if one.status == "confirmed" else " (proposed, not confirmed)"
        stance = {
            2: "loves it",
            1: "likes it",
            0: "neutral",
            -1: "not their thing",
            -2: "does not want it",
        }[one.stance]
        lines.append(f"- [{FACETS[one.facet]}] {one.label}: {stance}{mark}")
    return lines or ["(You do not know anything of their tastes yet.)"]
