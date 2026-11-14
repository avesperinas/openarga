from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from arga_tenancy import kernel_url
from hub import ai, banks, catalogue, claude_run, connections, credentials, plugs, sync
from hub.db import as_module
from hub.providers import (
    SourceError,
    books,
    claude,
    films,
    food,
    fx,
    github,
    maps,
    nearby,
    places,
    podcasts,
    routes,
    weather,
    wikimedia,
)

Handler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def source_transport() -> httpx.AsyncBaseTransport | None:
    return None


def kernel_transport() -> httpx.AsyncBaseTransport | None:
    return None


class Handoff(BaseModel):
    connection: UUID | None = None
    label: str | None = None
    secrets: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    consent_expires_at: datetime | None = None


FIND = text("select id from hub.hub_connection where id = :id and provider = :provider")


def handoff(provider: str) -> Handler:
    async def run(module: str, body: dict[str, Any]) -> dict[str, Any]:
        request = Handoff.model_validate(body)
        single = catalogue.provider(provider).single
        async with as_module() as database:
            if request.connection is not None:
                existing = await database.scalar(
                    FIND, {"id": request.connection, "provider": provider}
                )
            else:
                existing = await connections.first_of(database, provider) if single else None
            if existing is not None:
                return {"connection": str(existing), "created": False}
            created = await connections.create(
                database,
                provider,
                request.label,
                request.secrets,
                connection_id=request.connection,
                from_app=module,
                config=request.config,
                consent_expires_at=request.consent_expires_at,
            )
            found = await connections.detail(database, created)
        print(f"handover of {provider} from {module}: connection {created}", flush=True)
        async with httpx.AsyncClient(
            base_url=kernel_url(), transport=kernel_transport(), timeout=30.0
        ) as kernel:
            if provider == banks.PROVIDER:
                await sync.publish_events(
                    kernel, provider, banks.account_events(created, request.config)
                )
            await sync.announce_connection(kernel, found)
        return {"connection": str(created), "created": True}

    return run


class PingIn(BaseModel):
    connection: UUID
    key: Annotated[str, Field(min_length=1, max_length=200)]
    trigger: Literal["scheduled", "manual"]
    request_id: str | None = None


CONNECTION = text("""
    select id, provider, label, paused from hub.hub_connection
    where id = :id and provider = 'claude'
""")

PREVIOUS = text("""
    select outcome, detail from hub.hub_run
    where connection_id = :connection and idempotency_key = :key
""")


async def ping(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = PingIn.model_validate(body)
    provider = catalogue.provider("claude")
    async with as_module() as database:
        connection = (await database.execute(CONNECTION, {"id": request.connection})).one_or_none()
        if connection is None:
            raise connections.Refused("that Claude account is not in Hub", 404)
        run_id = await sync.start(database, connection.id, "action", "ping", request.key)
        if run_id is None:
            previous = (
                await database.execute(PREVIOUS, {"connection": connection.id, "key": request.key})
            ).one()
            return {"outcome": previous.outcome, "detail": previous.detail, "repeated": True}
        secrets = await sync.secrets_of(database, provider, connection.id)

    result = sync.Outcome(run_id, "ok")
    async with (
        httpx.AsyncClient(transport=source_transport()) as source,
        httpx.AsyncClient(
            base_url=kernel_url(), transport=kernel_transport(), timeout=30.0
        ) as kernel,
    ):
        if connection.paused:
            result.outcome = "skipped"
            result.detail = "Paused: nothing runs until you resume it in Hub."
        elif not sync.missing_credential(provider, secrets, result):
            started_at = datetime.now(UTC)
            said = await claude.message(source, secrets[claude.TOKEN] or "")
            event = claude.ping_event(
                request.key,
                request.trigger,
                str(connection.id),
                request.request_id,
                started_at,
                said,
            )
            try:
                await sync.publish_all(kernel, provider.id, [event], result)
            except httpx.HTTPError as error:
                result.detail = f"Started, but the kernel did not record it: {type(error).__name__}"
            if not said.success:
                result.outcome = "rate_limited" if said.rate_limited else "error"
                result.detail = said.first_line
        await sync.finish(kernel, connection, provider.id, "action", "ping", result)
    return {
        "outcome": result.outcome,
        "detail": result.detail,
        "code": result.code,
        "repeated": False,
    }


class SearchIn(BaseModel):
    query: Annotated[str, Field(min_length=2, max_length=60)]
    limit: Annotated[int, Field(ge=1, le=25)] = 10


LOOKUP = text("""
    select id, label, paused from hub.hub_connection
    where provider = :provider order by created_at limit 1
""")

LOOKED_UP = text("""
    insert into hub.hub_run
        (connection_id, capability, operation, outcome, finished_at, detail)
    values (:connection, 'lookup', 'search', :outcome, now(), :detail)
""")


async def food_search(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = SearchIn.model_validate(body)
    async with as_module() as database:
        usda = (await database.execute(LOOKUP, {"provider": "usda"})).one_or_none()
        off = (await database.execute(LOOKUP, {"provider": "openfoodfacts"})).one_or_none()
        if off is None:
            await connections.create(database, "openfoodfacts", None, {}, from_app=module)
            off = (await database.execute(LOOKUP, {"provider": "openfoodfacts"})).one()
        key = (
            await credentials.use(database, "usda", usda.id, "api_key")
            if usda is not None and not usda.paused
            else None
        )

    found: list[food.Candidate] = []
    failed: list[dict[str, str]] = []
    outcomes: list[tuple[UUID, str, str | None]] = []
    async with httpx.AsyncClient(transport=source_transport()) as client:
        asked: list[tuple[str, Any, Awaitable[list[food.Candidate]]]] = []
        if usda is None:
            failed.append({"source": "usda", "reason": "no USDA key: add it in Hub"})
        elif usda.paused:
            failed.append({"source": "usda", "reason": "USDA is paused in Hub"})
        elif (hit := food.cached("usda", request.query, request.limit)) is not None:
            found.extend(hit)
        else:
            asked.append(
                ("usda", usda, food.search_usda(client, key or "", request.query, request.limit))
            )
        if off.paused:
            reason = "Open Food Facts is paused in Hub"
            failed.append({"source": "off", "reason": reason})
        elif (hit := food.cached("off", request.query, request.limit)) is not None:
            found.extend(hit)
        else:
            asked.append(("off", off, food.search_off(client, request.query, request.limit)))

        answers = await asyncio.gather(*(call for _, _, call in asked), return_exceptions=True)
        for (name, row, _), answer in zip(asked, answers, strict=True):
            if isinstance(answer, food.SourceFailed):
                reason = str(answer)
            elif isinstance(answer, BaseException):
                reason = f"{'USDA' if name == 'usda' else 'OpenFoodFacts'} gave an answer that "
                reason += f"cannot be read ({type(answer).__name__})"
            else:
                food.remember(name, request.query, request.limit, answer)
                found.extend(answer)
                outcomes.append((row.id, "ok", None))
                continue
            failed.append({"source": name, "reason": reason})
            outcomes.append((row.id, "error", reason))
    async with as_module() as database:
        for connection_id, outcome, detail in outcomes:
            await database.execute(
                LOOKED_UP, {"connection": connection_id, "outcome": outcome, "detail": detail}
            )
    found.sort(key=lambda candidate: candidate.source != "usda")
    kept, discarded = food.sieve(found)
    return {
        "candidates": [food.as_dict(candidate) for candidate in kept],
        "failed": failed,
        "discarded": discarded,
    }


class FoodRef(BaseModel):
    source: Annotated[str, Field(pattern="^(usda|off)$")]
    source_ref: Annotated[str, Field(min_length=1, max_length=40)]


class FoodGetIn(BaseModel):
    items: Annotated[list[FoodRef], Field(min_length=1, max_length=25)]


async def food_get(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = FoodGetIn.model_validate(body)
    wanted = {
        name: [one.source_ref for one in request.items if one.source == name]
        for name in ("usda", "off")
    }
    async with as_module() as database:
        usda = (await database.execute(LOOKUP, {"provider": "usda"})).one_or_none()
        off = (await database.execute(LOOKUP, {"provider": "openfoodfacts"})).one_or_none()
        key = (
            await credentials.use(database, "usda", usda.id, "api_key")
            if usda is not None and not usda.paused and wanted["usda"]
            else None
        )

    candidates: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    discarded: list[dict[str, str]] = []
    outcomes: list[tuple[UUID, str, str | None]] = []
    async with httpx.AsyncClient(transport=source_transport()) as client:
        for name, row, fetch in (
            ("usda", usda, lambda: food.get_usda(client, key or "", wanted["usda"])),
            ("off", off, lambda: food.get_off(client, wanted["off"])),
        ):
            if not wanted[name]:
                continue
            if row is None or row.paused:
                failed.append({"source": name, "reason": f"{name} is not connected or is paused"})
                continue
            try:
                answer = await fetch()
            except food.SourceFailed as error:
                failed.append({"source": name, "reason": str(error)})
                outcomes.append((row.id, "error", str(error)))
                continue
            kept, dropped = food.sieve(answer)
            candidates.extend(food.as_dict(candidate) for candidate in kept)
            discarded.extend(dropped)
            outcomes.append((row.id, "ok", None))
    async with as_module() as database:
        for connection_id, outcome, detail in outcomes:
            await database.execute(
                LOOKED_UP, {"connection": connection_id, "outcome": outcome, "detail": detail}
            )
    return {"candidates": candidates, "failed": failed, "discarded": discarded}


class BookSearchIn(BaseModel):
    query: Annotated[str, Field(min_length=2, max_length=120)]
    limit: Annotated[int, Field(ge=1, le=25)] = 10


async def _lookup_connection(database, provider: str, module: str, automatic: bool):
    row = (await database.execute(LOOKUP, {"provider": provider})).one_or_none()
    if row is None and automatic:
        await connections.create(database, provider, None, {}, from_app=module)
        row = (await database.execute(LOOKUP, {"provider": provider})).one()
    return row


async def book_search(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = BookSearchIn.model_validate(body)
    async with as_module() as database:
        library = await _lookup_connection(database, "openlibrary", module, automatic=True)
        google = await _lookup_connection(database, "google_books", module, automatic=False)
        key = (
            await credentials.use(database, "google_books", google.id, "api_key")
            if google is not None and not google.paused
            else None
        )

    calls: list[tuple[str, Any, Awaitable[list[books.Candidate]] | None, str | None]] = []
    async with httpx.AsyncClient(transport=source_transport()) as client:
        if library.paused:
            calls.append(("openlibrary", library, None, "Open Library is paused in Hub"))
        else:
            search = books.search_openlibrary(client, request.query, request.limit)
            calls.append(("openlibrary", library, search, None))
        if google is None:
            calls.append(("google_books", None, None, "no Google Books key: add it in Hub"))
        elif google.paused:
            calls.append(("google_books", google, None, "Google Books is paused in Hub"))
        else:
            search = books.search_google(client, key or "", request.query, request.limit)
            calls.append(("google_books", google, search, None))
        pending = [call for _, _, call, _ in calls if call is not None]
        answers = iter(await asyncio.gather(*pending, return_exceptions=True))

        candidates: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        outcomes: list[tuple[UUID, str, str | None]] = []
        for name, row, call, reason in calls:
            if call is None:
                failed.append({"source": name, "reason": reason or ""})
                continue
            answer = next(answers)
            if isinstance(answer, books.SourceFailed):
                failed.append({"source": name, "reason": str(answer)})
                outcomes.append((row.id, "error", str(answer)))
            elif isinstance(answer, BaseException):
                raise answer
            else:
                candidates.extend(books.as_dict(candidate) for candidate in answer)
                outcomes.append((row.id, "ok", None))
    async with as_module() as database:
        for connection_id, outcome, detail in outcomes:
            await database.execute(
                LOOKED_UP, {"connection": connection_id, "outcome": outcome, "detail": detail}
            )
    return {"candidates": candidates, "failed": failed}


class CoverIn(BaseModel):
    source: Literal["openlibrary", "google_books"]
    ref: Annotated[str, Field(min_length=1, max_length=40)]


async def book_cover(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = CoverIn.model_validate(body)
    try:
        books.cover_request(request.source, request.ref)
    except books.SourceFailed as error:
        raise connections.Refused(str(error), 422) from error
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            found = await books.fetch_cover(client, request.source, request.ref)
    except books.SourceFailed as error:
        return {"cover": None, "type": None, "failed": str(error)}
    if found is None:
        return {"cover": None, "type": None, "failed": None}
    body_bytes, kind = found
    return {"cover": base64.b64encode(body_bytes).decode("ascii"), "type": kind, "failed": None}


class PlaceSearchIn(BaseModel):
    query: Annotated[str, Field(min_length=2, max_length=120)]
    limit: Annotated[int, Field(ge=1, le=10)] = 5


async def places_search(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = PlaceSearchIn.model_validate(body)
    async with as_module() as database:
        row = (await database.execute(LOOKUP, {"provider": "nominatim"})).one_or_none()
        if row is None:
            await connections.create(database, "nominatim", None, {}, from_app=module)
            row = (await database.execute(LOOKUP, {"provider": "nominatim"})).one()
    if row.paused:
        return {
            "candidates": [],
            "failed": [{"source": "nominatim", "reason": "OpenStreetMap is paused in Hub"}],
        }

    candidates: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    async with httpx.AsyncClient(transport=source_transport()) as client:
        try:
            found = await places.search(client, request.query, request.limit)
            candidates = [places.as_dict(one) for one in found]
            outcome, detail = "ok", None
        except places.SourceFailed as error:
            failed.append({"source": "nominatim", "reason": str(error)})
            outcome, detail = "error", str(error)
    async with as_module() as database:
        await database.execute(
            LOOKED_UP, {"connection": row.id, "outcome": outcome, "detail": detail}
        )
    return {"candidates": candidates, "failed": failed}


async def _lookup_row(module: str, provider: str):
    async with as_module() as database:
        row = (await database.execute(LOOKUP, {"provider": provider})).one_or_none()
        if row is None:
            await connections.create(database, provider, None, {}, from_app=module)
            row = (await database.execute(LOOKUP, {"provider": provider})).one()
    return row


async def _looked_up(row, outcome: str, detail: str | None) -> None:
    async with as_module() as database:
        await database.execute(
            LOOKED_UP, {"connection": row.id, "outcome": outcome, "detail": detail}
        )


class TileIn(BaseModel):
    z: Annotated[int, Field(ge=0, le=maps.MAX_ZOOM)]
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def inside(self) -> TileIn:
        if self.x >= 1 << self.z or self.y >= 1 << self.z:
            raise ValueError("that tile does not exist at that zoom")
        return self


TILE_NOTED_SECONDS = 600
_tile_noted: dict[str, float | None] = {"at": None}


async def maps_tile(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = TileIn.model_validate(body)
    row = await _lookup_row(module, "protomaps")
    if row.paused:
        return {"tile": None, "build": None, "failed": "Protomaps is paused in Hub"}
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            found = await maps.tile(client, request.z, request.x, request.y)
    except maps.SourceFailed as error:
        _tile_noted["at"] = None
        await _looked_up(row, "error", str(error))
        return {"tile": None, "build": None, "failed": str(error)}
    last = _tile_noted["at"]
    if last is None or time.monotonic() - last > TILE_NOTED_SECONDS:
        _tile_noted["at"] = time.monotonic()
        await _looked_up(row, "ok", None)
    return {
        "tile": base64.b64encode(found).decode("ascii") if found is not None else None,
        "build": maps.build(),
        "failed": None,
    }


MAPS_RECHECK_SECONDS = 3600

LAST_LOOKUP = text("""
    select outcome, started_at from hub.hub_run
    where connection_id = :connection order by started_at desc limit 1
""")


async def maps_recheck(source: httpx.AsyncClient) -> str | None:
    async with as_module() as database:
        row = (await database.execute(LOOKUP, {"provider": "protomaps"})).one_or_none()
        if row is None or row.paused:
            return None
        last = (await database.execute(LAST_LOOKUP, {"connection": row.id})).one_or_none()
    if last is None or last.outcome != "error":
        return None
    if (datetime.now(UTC) - last.started_at).total_seconds() < MAPS_RECHECK_SECONDS:
        return None
    try:
        await maps.check(source)
    except maps.SourceFailed as error:
        await _looked_up(row, "error", str(error))
        return "error"
    await _looked_up(row, "ok", None)
    return "ok"


class DirectionsIn(BaseModel):
    profile: routes.Profile = "foot"
    points: Annotated[list[tuple[float, float]], Field(min_length=2, max_length=25)]

    @model_validator(mode="after")
    def on_earth(self) -> DirectionsIn:
        for lon, lat in self.points:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("a point outside the world")
        return self


async def routes_directions(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = DirectionsIn.model_validate(body)
    row = await _lookup_row(module, "osrm")
    if row.paused:
        return {"route": None, "failed": "Routes are paused in Hub"}
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            found = await routes.directions(client, request.profile, request.points)
    except routes.SourceFailed as error:
        await _looked_up(row, "error", str(error))
        return {"route": None, "failed": str(error)}
    await _looked_up(row, "ok", None)
    return {"route": found, "failed": None}


class NearbyIn(BaseModel):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    kind: nearby.Kind = "sights"
    radius: Annotated[int, Field(ge=100, le=3000)] = 1000
    limit: Annotated[int, Field(ge=1, le=30)] = 15


async def places_nearby(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = NearbyIn.model_validate(body)
    row = await _lookup_row(module, "overpass")
    if row.paused:
        return {"places": [], "failed": "Nearby places are paused in Hub"}
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            found = await nearby.around(
                client, request.kind, request.lat, request.lon, request.radius, request.limit
            )
    except nearby.SourceFailed as error:
        await _looked_up(row, "error", str(error))
        return {"places": [], "failed": str(error)}
    await _looked_up(row, "ok", None)
    return {"places": [nearby.as_dict(one) for one in found], "failed": None}


class WeatherIn(BaseModel):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


async def _weather(module: str, body: dict[str, Any], climate: bool) -> dict[str, Any]:
    request = WeatherIn.model_validate(body)
    row = await _lookup_row(module, "open_meteo")
    if row.paused:
        return {"weather": None, "failed": "Weather is paused in Hub"}
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            if climate:
                found = await weather.climate(
                    client, request.lat, request.lon, datetime.now(UTC).date()
                )
            else:
                found = await weather.forecast(client, request.lat, request.lon)
    except weather.SourceFailed as error:
        await _looked_up(row, "error", str(error))
        return {"weather": None, "failed": str(error)}
    await _looked_up(row, "ok", None)
    return {"weather": found, "failed": None}


async def weather_forecast(module: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _weather(module, body, climate=False)


async def weather_climate(module: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _weather(module, body, climate=True)


class RateIn(BaseModel):
    currency: Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")]
    day: date | None = None


async def fx_rate(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = RateIn.model_validate(body)
    today = datetime.now(UTC).date()
    if request.currency.upper() == "EUR":
        return {"rate": 1.0, "date": (request.day or today).isoformat(), "failed": None}
    row = await _lookup_row(module, "frankfurter")
    if row.paused:
        return {"rate": None, "date": None, "failed": "Exchange rates are paused in Hub"}
    try:
        async with httpx.AsyncClient(transport=source_transport()) as client:
            found = await fx.rate(client, request.currency, request.day or today, today)
    except fx.SourceFailed as error:
        await _looked_up(row, "error", str(error))
        return {"rate": None, "date": None, "failed": str(error)}
    await _looked_up(row, "ok", None)
    return {"rate": found["rate"], "date": found["date"], "failed": None}


class PlacePhotoIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    place: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    osm_ref: Annotated[str, Field(pattern=r"^(node|way|relation)/[0-9]+$")] | None = None
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lon: Annotated[float, Field(ge=-180, le=180)] | None = None


async def place_photo(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = PlacePhotoIn.model_validate(body)
    async with as_module() as database:
        row = (await database.execute(LOOKUP, {"provider": "wikimedia"})).one_or_none()
        if row is None:
            await connections.create(database, "wikimedia", None, {}, from_app=module)
            row = (await database.execute(LOOKUP, {"provider": "wikimedia"})).one()
    if row.paused:
        return {"photo": None, "failed": "Wikimedia is paused in Hub"}
    found, failed = None, None
    async with httpx.AsyncClient(transport=source_transport()) as client:
        try:
            found = await wikimedia.photo(
                client, request.name, request.place, request.osm_ref, request.lat, request.lon
            )
        except wikimedia.SourceFailed as error:
            failed = str(error)
    async with as_module() as database:
        await database.execute(
            LOOKED_UP,
            {"connection": row.id, "outcome": "error" if failed else "ok", "detail": failed},
        )
    if found is None:
        return {"photo": None, "failed": failed}
    return {
        "photo": {
            "content": base64.b64encode(found.content).decode("ascii"),
            "type": found.type,
            "author": found.author,
            "license": found.license,
            "page": found.page,
        },
        "failed": None,
    }


class PodcastSearchIn(BaseModel):
    query: Annotated[str, Field(min_length=2, max_length=200)]
    kind: Literal["podcast", "episode"] = "podcast"
    limit: Annotated[int, Field(ge=1, le=15)] = 8


class FilmSearchIn(BaseModel):
    query: Annotated[str, Field(min_length=1, max_length=200)]
    kind: Literal["film", "series", "documentary"] = "film"
    limit: Annotated[int, Field(ge=1, le=15)] = 8


async def _automatic(module: str, provider: str):
    async with as_module() as database:
        return await _lookup_connection(database, provider, module, automatic=True)


async def podcast_search(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = PodcastSearchIn.model_validate(body)
    row = await _automatic(module, "apple_podcasts")
    if row.paused:
        return {"candidates": [], "failed": "Apple Podcasts is paused in Hub"}
    found, failed = [], None
    async with httpx.AsyncClient(transport=source_transport()) as client:
        try:
            found = await podcasts.search(client, request.query, request.kind, request.limit)
        except podcasts.SourceFailed as error:
            failed = str(error)
    await _looked_up(row, "error" if failed else "ok", failed)
    return {"candidates": found, "failed": failed}


async def film_search(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = FilmSearchIn.model_validate(body)
    row = await _automatic(module, "wikidata")
    if row.paused:
        return {"candidates": [], "failed": "Wikidata is paused in Hub"}
    found, failed = [], None
    async with httpx.AsyncClient(transport=source_transport()) as client:
        try:
            found = await films.search(client, request.query, request.kind, request.limit)
        except films.SourceFailed as error:
            failed = str(error)
    await _looked_up(row, "error" if failed else "ok", failed)
    return {"candidates": found, "failed": failed}


def _offered(provider: str) -> catalogue.Provider:
    try:
        found = catalogue.provider(provider)
    except LookupError:
        found = None
    if found is None or found.offer is None or not found.available:
        known = ", ".join(one.id for one in catalogue.offered())
        raise connections.Refused(f"'{provider}' cannot be plugged in from an app: {known}")
    return found


async def _plug(
    module: str,
    provider_id: str,
    label: str,
    params: dict[str, Any],
    settings: dict[str, Any] | None,
    inlet_required: bool,
) -> dict[str, Any]:
    provider = _offered(provider_id)
    found_inlets = await plugs.inlets(kernel_transport())
    mine = plugs.accepting(provider, plugs.of_module(module, found_inlets))
    if inlet_required and not mine:
        raise connections.Refused(f"{provider.name} fits none of {module}'s plugs", 409)
    try:
        params = provider.clean(params) if provider.clean else {}
    except ValueError as error:
        raise connections.Refused(str(error)) from error
    answers = {inlet["key"]: settings or {} for inlet in mine}
    if mine:
        async with as_module() as database:
            existing = await database.scalar(
                SAME_PLUG,
                {
                    "provider": provider.id,
                    "config": json.dumps(params, sort_keys=True),
                    "inlet": mine[0]["key"],
                },
            )
            found = await connections.detail(database, existing) if existing else None
        if existing:
            return {
                "connection": str(existing),
                "label": found["label"] if found else label,
                "inlet": mine[0]["key"],
                "settings": (found or {}).get("plugs", {}).get(mine[0]["key"], {}),
                "existing": True,
            }
    async with as_module() as database:
        created = await connections.create(
            database,
            provider.id,
            label,
            {},
            from_app=module,
            config=params,
            plugs=plugs.plugs_for(provider, found_inlets, answers, label),
        )
        await connections.share(database, provider, created)
        found = await connections.detail(database, created)
    async with httpx.AsyncClient(
        base_url=kernel_url(), transport=kernel_transport(), timeout=30.0
    ) as kernel:
        await sync.announce_connection(kernel, found)
    return {
        "connection": str(created),
        "label": found["label"] if found else label,
        "inlet": mine[0]["key"] if mine else None,
        "settings": (found or {}).get("plugs", {}).get(mine[0]["key"], {}) if mine else {},
        "existing": False,
    }


SAME_PLUG = text("""
    select id from hub.hub_connection
    where provider = :provider
      and config = cast(:config as jsonb)
      and plugs ? :inlet
    limit 1
""")


class PlugIn(BaseModel):
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    params: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


async def sources_plug(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = PlugIn.model_validate(body)
    return await _plug(
        module, request.provider, request.label, request.params, request.settings, True
    )


async def sources_catalogue(module: str, body: dict[str, Any]) -> dict[str, Any]:
    mine = plugs.of_module(module, await plugs.inlets(kernel_transport()))
    contracts = {contract for inlet in mine for contract in inlet["contracts"]}
    return {
        "groups": plugs.groups(),
        "inlets": mine,
        "sources": [plugs.described(one, mine) for one in catalogue.offered(contracts)],
    }


class SearchSourceIn(BaseModel):
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")]
    ask: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,40}$")]
    query: Annotated[str, Field(max_length=60)] | None = None
    parent: Annotated[str, Field(max_length=60)] | None = None


async def search(provider_id: str, ask: str, query: str | None, parent: str | None) -> dict:
    provider = _offered(provider_id)
    found = provider.search_for(ask)
    if found is None:
        raise connections.Refused(f"{provider.name} does not search anything for '{ask}'")
    async with httpx.AsyncClient(transport=source_transport()) as client:
        try:
            results = await found(client, query, parent)
        except ValueError as error:
            raise connections.Refused(str(error)) from error
        except SourceError as error:
            return {"results": [], "failed": str(error)}
    return {"results": results, "failed": None}


async def sources_search(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = SearchSourceIn.model_validate(body)
    return await search(request.provider, request.ask, request.query, request.parent)


class UnplugIn(BaseModel):
    connection: UUID


CONNECTION_PROVIDER = text("""
    select provider from hub.hub_connection where id = :id
""")


async def _unplug(module: str, connection_id: UUID) -> dict[str, Any]:
    async with as_module() as database:
        provider_id = await database.scalar(CONNECTION_PROVIDER, {"id": connection_id})
        if provider_id is None:
            return {"removed": False}
        provider = catalogue.provider(provider_id)
        mine = plugs.of_module(module, await plugs.inlets(kernel_transport()))
        contracts = {contract for inlet in mine for contract in inlet["contracts"]}
        if provider.offer is None or not contracts & set(provider.emits):
            raise connections.Refused(f"{provider.name} cannot be removed from {module}")
        found = await connections.detail(database, connection_id)
        await connections.remove(database, connection_id)
    async with httpx.AsyncClient(
        base_url=kernel_url(), transport=kernel_transport(), timeout=30.0
    ) as kernel:
        await sync.announce_connection(kernel, found, True)
    print(f"plug {connection_id} removed from {module}", flush=True)
    return {"removed": True}


async def sources_unplug(module: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _unplug(module, UnplugIn.model_validate(body).connection)


class RefreshIn(BaseModel):
    connection: UUID
    search: bool = False


REFRESH_ROW = text("""
    select id, provider, label, status, paused, config
    from hub.hub_connection where id = :id
""")
FORCE_SEARCH = text("""
    update hub.hub_connection
    set config = config || '{"search_now": true}'::jsonb where id = :id
""")

RUNNING: set[asyncio.Task] = set()


async def sources_refresh(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = RefreshIn.model_validate(body)
    async with as_module() as database:
        row = (await database.execute(REFRESH_ROW, {"id": request.connection})).one_or_none()
        if row is None:
            raise connections.Refused("that connection does not exist", 404)
        provider = catalogue.provider(row.provider)
        mine = plugs.of_module(module, await plugs.inlets(kernel_transport()))
        contracts = {contract for inlet in mine for contract in inlet["contracts"]}
        if not contracts & set(provider.emits) or row.provider not in sync.CLIENTS:
            raise connections.Refused(f"{provider.name} cannot be updated from {module}", 409)
        if row.paused or row.status != "active":
            raise connections.Refused(f"{row.label} is not active in Hub", 409)
        if request.search:
            await database.execute(FORCE_SEARCH, {"id": request.connection})
            row = (await database.execute(REFRESH_ROW, {"id": request.connection})).one()

    async def run() -> None:
        async with (
            httpx.AsyncClient(transport=source_transport(), timeout=60.0) as client,
            httpx.AsyncClient(
                base_url=kernel_url(), transport=kernel_transport(), timeout=30.0
            ) as kernel,
        ):
            await sync.run(row, source=client, kernel=kernel)

    task = asyncio.create_task(run())
    RUNNING.add(task)
    task.add_done_callback(RUNNING.discard)
    return {"started": True, "connection": str(request.connection), "search": request.search}


class NoteFile(BaseModel):
    path: Annotated[str, Field(min_length=1, max_length=1200)]
    text: str | None = None
    base64: str | None = None


class NotesPushIn(BaseModel):
    key: Annotated[str, Field(min_length=1, max_length=200)]
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    files: list[NoteFile] = Field(default_factory=list, max_length=20000)
    deletes: list[Annotated[str, Field(min_length=1, max_length=1200)]] = Field(
        default_factory=list, max_length=20000
    )


GITHUB = text("""
    select id, provider, label, paused, config from hub.hub_connection
    where provider = 'github' order by created_at limit 1
""")


async def notes_push(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = NotesPushIn.model_validate(body)
    provider = catalogue.provider("github")
    async with as_module() as database:
        connection = (await database.execute(GITHUB)).one_or_none()
        if connection is None:
            raise connections.Refused("no GitHub repository is connected in Hub", 404)
        run_id = await sync.start(database, connection.id, "action", "push", request.key)
        if run_id is None:
            previous = (
                await database.execute(PREVIOUS, {"connection": connection.id, "key": request.key})
            ).one()
            return {"outcome": previous.outcome, "detail": previous.detail, "repeated": True}
        secrets = await sync.secrets_of(database, provider, connection.id)

    result = sync.Outcome(run_id, "ok")
    config = connection.config or {}
    pushed: github.Pushed | None = None
    async with (
        httpx.AsyncClient(transport=source_transport()) as source,
        httpx.AsyncClient(
            base_url=kernel_url(), transport=kernel_transport(), timeout=30.0
        ) as kernel,
    ):
        if connection.paused:
            result.outcome = "skipped"
            result.detail = "Paused: nothing is copied until you resume it in Hub."
        elif not sync.missing_credential(provider, secrets, result):
            change = github.Change(
                texts={f.path: f.text for f in request.files if f.text is not None},
                binaries={f.path: f.base64 for f in request.files if f.base64 is not None},
                deletes=list(request.deletes),
            )
            try:
                pushed = await github.push(
                    source,
                    secrets[github.TOKEN] or "",
                    config.get(github.REPO, ""),
                    config.get(github.BRANCH, "main"),
                    change,
                    request.message,
                )
                result.emitted = len(request.files) + len(request.deletes)
                result.detail = pushed.url
            except SourceError as error:
                result.outcome = "error"
                result.detail = str(error)
        await sync.finish(kernel, connection, provider.id, "action", "push", result)
    return {
        "outcome": result.outcome,
        "detail": result.detail,
        "commit": pushed.commit if pushed else None,
        "url": pushed.url if pushed else None,
        "repeated": False,
    }


CAPABILITIES: dict[str, Handler] = {
    "ai.extract": ai.extract,
    "ai.run": ai.run,
    "bitvavo.handoff": handoff("bitvavo"),
    "enable_banking.handoff": handoff("enable_banking"),
    "claude.handoff": handoff("claude"),
    "claude.ping": ping,
    "claude.run": claude_run.request,
    "food.search": food_search,
    "food.get": food_get,
    "books.search": book_search,
    "books.cover": book_cover,
    "podcasts.search": podcast_search,
    "films.search": film_search,
    "places.search": places_search,
    "places.photo": place_photo,
    "maps.tile": maps_tile,
    "fx.rate": fx_rate,
    "weather.forecast": weather_forecast,
    "weather.climate": weather_climate,
    "places.nearby": places_nearby,
    "routes.directions": routes_directions,
    "sources.catalogue": sources_catalogue,
    "sources.search": sources_search,
    "sources.plug": sources_plug,
    "sources.unplug": sources_unplug,
    "sources.refresh": sources_refresh,
    "notes.push": notes_push,
    "usda.handoff": handoff("usda"),
}
