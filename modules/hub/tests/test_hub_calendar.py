from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import capabilities, catalogue, sync
from hub.providers import SourceError, calendars, football, formula1, holidays, ical

TOKEN = secrets.token_hex(16)
TODAY = date(2026, 9, 28)

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//arga//pruebas//ES
X-WR-TIMEZONE:Europe/Madrid
BEGIN:VEVENT
UID:clase@pruebas
DTSTART;TZID=Europe/Madrid:20261005T190000
DTEND;TZID=Europe/Madrid:20261005T200000
RRULE:FREQ=WEEKLY;COUNT=3
SUMMARY:Clase de prueba
LOCATION:Study 1
END:VEVENT
BEGIN:VEVENT
UID:clase@pruebas
RECURRENCE-ID;TZID=Europe/Madrid:20261012T190000
DTSTART;TZID=Europe/Madrid:20261012T180000
DTEND;TZID=Europe/Madrid:20261012T190000
SUMMARY:Clase de prueba (adelantada)
END:VEVENT
BEGIN:VEVENT
UID:fiesta@pruebas
DTSTART;VALUE=DATE:20261012
SUMMARY:Fiesta de prueba
URL:https://example.org/fiesta
END:VEVENT
BEGIN:VEVENT
UID:suelta@pruebas
DTSTART:20261101T100000
SUMMARY:Hora flotante
END:VEVENT
BEGIN:VEVENT
UID:vieja@pruebas
DTSTART;VALUE=DATE:20200101
SUMMARY:Fuera de la ventana
END:VEVENT
END:VCALENDAR
"""


def test_an_ics_is_read_whole_with_its_series_expanded() -> None:
    items = {item.uid: item for item in ical.parse(ICS, TODAY)}

    series = sorted(uid for uid in items if uid.startswith("clase@"))
    assert len(series) == 3
    moved = items["clase@pruebas#20261012T170000Z"]
    assert moved.title == "Clase de prueba (adelantada)"
    assert moved.start == "2026-10-12T18:00:00+02:00"
    assert moved.tz == "Europe/Madrid"
    first = items["clase@pruebas#20261005T170000Z"]
    assert (first.location, first.end) == ("Study 1", "2026-10-05T20:00:00+02:00")

    party = items["fiesta@pruebas"]
    assert (party.all_day, party.start, party.end) == (True, "2026-10-12", "2026-10-13")
    assert party.url == "https://example.org/fiesta"
    loose = items["suelta@pruebas"]
    assert loose.start == loose.end == "2026-11-01T10:00:00+01:00"


def test_what_falls_outside_the_window_is_left_out() -> None:
    connection = SimpleNamespace(id=UUID(int=1), label="Pruebas")
    found = calendars.events(
        connection, "ical", ical.parse(ICS, TODAY), datetime.fromisoformat("2026-09-28T10:00+00:00")
    )

    uids = {event["payload"]["uid"] for event in found if event["type"] == calendars.EVENT}
    assert "vieja@pruebas" not in uids
    feed = found[-1]
    assert feed["type"] == calendars.FEED
    assert set(feed["payload"]["events"]) == uids
    assert (feed["payload"]["from"], feed["payload"]["to"]) == ("2025-01-01", "2028-09-27")


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("webcal://example.org/a.ics", "https://example.org/a.ics"),
        ("  https://example.org/a.ics ", "https://example.org/a.ics"),
    ],
)
def test_a_webcal_address_is_an_https_one(raw, clean) -> None:
    assert ical.clean_url(raw) == clean


@pytest.mark.parametrize("raw", ["", "example.org/a.ics", "ftp://example.org/a.ics", "file:///x"])
def test_an_address_that_cannot_be_asked_is_refused(raw) -> None:
    with pytest.raises(ValueError):
        ical.clean_url(raw)


def test_something_that_is_not_a_calendar_is_said() -> None:
    with pytest.raises(SourceError):
        ical.parse(b"<html>no</html>", TODAY)


NAGER = [
    {
        "date": "2026-01-01",
        "localName": "Año Nuevo",
        "name": "New Year",
        "global": True,
        "counties": None,
        "types": ["Public"],
    },
    {
        "date": "2026-04-06",
        "localName": "Lunes de Pascua",
        "name": "Easter Monday",
        "global": False,
        "counties": ["ES-NC", "ES-PV"],
        "types": ["Public"],
    },
    {
        "date": "2026-04-23",
        "localName": "Otra fiesta",
        "name": "Other",
        "global": False,
        "counties": ["ES-AR"],
        "types": ["Public"],
    },
    {
        "date": "2026-05-02",
        "localName": "Solo de bancos",
        "name": "Bank",
        "global": True,
        "counties": None,
        "types": ["Bank"],
    },
]


def test_a_region_brings_the_national_ones_and_its_own() -> None:
    titles = [item.title for item in holidays.items_of(NAGER, "ES", "ES-NC")]

    assert titles == ["Año Nuevo", "Lunes de Pascua"]
    assert [item.title for item in holidays.items_of(NAGER, "ES", None)] == ["Año Nuevo"]
    [easter] = [i for i in holidays.items_of(NAGER, "ES", "ES-NC") if i.title == "Lunes de Pascua"]
    assert (easter.all_day, easter.start, easter.end) == (True, "2026-04-06", "2026-04-07")
    assert easter.description == "Festivo en Navarra, País Vasco"


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ({"country": "es"}, {"country": "ES", "region": None}),
        ({"country": "ES", "region": "es-nc"}, {"country": "ES", "region": "ES-NC"}),
    ],
)
def test_holiday_parameters(raw, clean) -> None:
    assert holidays.clean_settings(raw) == clean


@pytest.mark.parametrize("raw", [{}, {"country": "España"}, {"country": "ES", "region": "FR-X"}])
def test_holiday_parameters_that_make_no_sense(raw) -> None:
    with pytest.raises(ValueError):
        holidays.clean_settings(raw)


async def test_a_pass_of_holidays_also_lists_them_by_day_before_the_feed() -> None:
    from arga_contracts import sources

    connection = SimpleNamespace(
        id=UUID(int=3),
        label="Festivos · Navarra",
        provider="holidays",
        config={"country": "ES", "region": "ES-NC"},
    )

    async def answer(request: httpx.Request) -> httpx.Response:
        found = NAGER if request.url.path.endswith("/2026/ES") else []
        return httpx.Response(200, json=found)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        found = await holidays.sync(client, {}, connection)

    assert [one["type"] for one in found][-2:] == ["calendar.holidays", "calendar.feed"]
    listed = found[-2]["payload"]
    sources.check("calendar.holidays", listed)
    assert listed["days"] == {"2026-01-01": "Año Nuevo", "2026-04-06": "Lunes de Pascua"}
    assert (listed["country"], listed["region"]) == ("ES", "ES-NC")


RACE = {
    "season": "2026",
    "round": "7",
    "url": "https://example.org/gp",
    "raceName": "Spanish Grand Prix",
    "Circuit": {
        "circuitName": "Circuito de prueba",
        "Location": {"locality": "Villa", "country": "Spain"},
    },
    "date": "2026-06-14",
    "time": "13:00:00Z",
    "FirstPractice": {"date": "2026-06-12", "time": "11:30:00Z"},
    "Qualifying": {"date": "2026-06-13", "time": "14:00:00Z"},
    "Sprint": {"date": "2026-06-13", "time": "10:00:00Z"},
}


def test_formula1_brings_the_chosen_sessions_in_utc() -> None:
    items = formula1.items_of([RACE], ["race", "qualifying"])

    assert [item.title for item in items] == [
        "GP de España · Carrera",
        "GP de España · Clasificación",
    ]
    race = items[0]
    assert (race.uid, race.start, race.end) == (
        "f1:2026:7:race",
        "2026-06-14T13:00:00+00:00",
        "2026-06-14T15:00:00+00:00",
    )
    assert race.location == "Circuito de prueba, Villa"
    everything = formula1.items_of([RACE], list(formula1.SESSIONS))
    assert len(everything) == 4


def test_formula1_sessions_by_default_and_by_name() -> None:
    assert formula1.clean_settings({}) == {"sessions": ["race", "qualifying", "sprint"]}
    assert formula1.clean_settings({"sessions": "practice, race"}) == {
        "sessions": ["race", "practice"]
    }
    with pytest.raises(ValueError):
        formula1.clean_settings({"sessions": ["podium"]})


def espn(event_id: str, when: str, home: str, away: str, **extra) -> dict:
    status = extra.pop("status", "STATUS_SCHEDULED")
    scores = extra.pop("scores", (None, None))
    return {
        "id": event_id,
        "date": when,
        "timeValid": extra.pop("timed", True),
        "competitions": [
            {
                "status": {"type": {"name": status}},
                "venue": {"fullName": "Estadio de prueba", "address": {"city": "Villa"}},
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"displayName": home},
                        "score": {"displayValue": scores[0]} if scores[0] else None,
                    },
                    {
                        "homeAway": "away",
                        "team": {"displayName": away},
                        "score": {"displayValue": scores[1]} if scores[1] else None,
                    },
                ],
            }
        ],
    }


def test_a_match_is_home_against_away_with_its_competition() -> None:
    [played, fixed, open_, postponed] = football.items_of(
        [
            espn(
                "1",
                "2026-08-24T17:30Z",
                "Local FC",
                "Visitante CF",
                status="STATUS_FULL_TIME",
                scores=("2", "1"),
            ),
            espn("2", "2026-10-18T12:00Z", "Visitante CF", "Local FC"),
            espn("3", "2027-05-23T18:00Z", "Local FC", "Otro CF", timed=False),
            espn("4", "2026-11-01T15:00Z", "Local FC", "Otro CF", status="STATUS_POSTPONED"),
        ],
        "LaLiga",
    )

    assert (played.uid, played.title) == ("espn:1", "Local FC – Visitante CF")
    assert played.description == "LaLiga · 2–1"
    assert (fixed.start, fixed.end) == ("2026-10-18T12:00:00+00:00", "2026-10-18T14:00:00+00:00")
    assert fixed.location == "Estadio de prueba, Villa"
    assert (open_.all_day, open_.start, open_.end) == (True, "2027-05-23", "2027-05-24")
    assert open_.description == "LaLiga · hora por confirmar"
    assert postponed.status == "cancelled"


def test_when_the_hour_is_fixed_the_match_changes_and_keeps_its_uid() -> None:
    before = football.items_of([espn("3", "2027-05-23T18:00Z", "A", "B", timed=False)], "LaLiga")
    after = football.items_of([espn("3", "2027-05-23T19:00Z", "A", "B")], "LaLiga")

    assert before[0].uid == after[0].uid
    assert before[0].fingerprint() != after[0].fingerprint()


def test_football_parameters() -> None:
    assert football.clean_settings({"team": "97", "team_name": " Equipo  X "}) == {
        "team": "97",
        "league": "esp.1",
        "team_name": "Equipo X",
    }
    for raw in ({}, {"team": "abc"}, {"team": "97", "league": "mars.1"}):
        with pytest.raises(ValueError):
            football.clean_settings(raw)


def test_a_team_brings_its_league_its_cup_and_europe() -> None:
    assert list(football.competitions("esp.1")) == [
        "esp.1",
        "esp.copa_del_rey",
        "uefa.champions",
        "uefa.europa",
        "uefa.europa.conf",
    ]


async def test_a_team_is_found_by_its_name_without_accents() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esp.1/teams"):
            teams = [
                {"team": {"id": "11", "displayName": "Club Atlético Inventado"}},
                {"team": {"id": "12", "displayName": "Otro Club"}},
            ]
            return httpx.Response(200, json={"sports": [{"leagues": [{"teams": teams}]}]})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        found = await football.teams(client, "atletico")

    assert found == [
        {
            "code": "11",
            "name": "Club Atlético Inventado",
            "league": "esp.1",
            "league_name": "LaLiga",
            "detail": "LaLiga",
        }
    ]


async def test_without_its_league_the_pass_fails_and_without_a_cup_it_does_not() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if "/esp.1/" in request.url.path:
            return httpx.Response(200, json={"events": [espn("9", "2026-10-18T12:00Z", "A", "B")]})
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        items = await football.fetch(client, "11", "esp.1")
    assert [item.uid for item in items] == ["espn:9"]

    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(down)) as client:
        with pytest.raises(SourceError):
            await football.fetch(client, "11", "esp.1")


def test_the_calendar_category_and_its_providers_are_in_the_catalogue() -> None:
    [category] = [c for c in catalogue.listed() if c["id"] == "calendar"]
    assert [p["id"] for p in category["providers"]] == [
        "holidays",
        "formula1",
        "football",
        "ical",
        "ical_private",
    ]
    assert all(p["available"] for p in category["providers"])


class Source:
    def __init__(self) -> None:
        self.body = ICS
        self.status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self.status, content=self.body)


@pytest.fixture
def served() -> Source:
    return Source()


@pytest.fixture
async def source(served):
    async with httpx.AsyncClient(transport=httpx.MockTransport(served)) as client:
        yield client


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
    await kernel_db.engine().dispose()


async def subscribe(api, url: str = "webcal://example.org/pruebas.ics") -> dict:
    response = await api.post(
        "/connections", json={"provider": "ical", "label": "Pruebas", "settings": {"url": url}}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def pass_of(connection: dict, source, kernel) -> sync.Outcome:
    async def no_wait(_: float) -> None:
        return None

    row = SimpleNamespace(
        id=UUID(connection["id"]),
        provider="ical",
        label=connection["label"],
        config={"url": "https://example.org/pruebas.ics"},
    )
    return await sync.run(row, source=source, kernel=kernel, sleep=no_wait, attempts=1)


async def published(schema, event_type: str) -> list:
    async with schema.connect() as connection:
        return (
            (
                await connection.execute(
                    text(
                        "select payload from kernel.events "
                        "where module = 'hub' and type = :type order by ts, ingested_at"
                    ),
                    {"type": event_type},
                )
            )
            .scalars()
            .all()
        )


async def test_a_pass_publishes_every_event_and_then_the_feed(api, schema, kernel, source) -> None:
    connection = await subscribe(api)

    outcome = await pass_of(connection, source, kernel)

    assert outcome.outcome == "ok", outcome.detail
    events = await published(schema, calendars.EVENT)
    [feed] = await published(schema, calendars.FEED)
    assert outcome.emitted == len(events) + 1
    assert {e["uid"] for e in events} == set(feed["events"])
    assert all(e["connection"] == connection["id"] for e in events)
    assert feed["label"] == "Pruebas"


async def test_what_does_not_change_does_not_come_in_again(api, schema, kernel, source, served):
    connection = await subscribe(api)
    await pass_of(connection, source, kernel)
    before = len(await published(schema, calendars.EVENT))

    served.body = ICS.replace(b"SUMMARY:Fiesta de prueba", b"SUMMARY:Fiesta cambiada")
    await pass_of(connection, source, kernel)

    events = await published(schema, calendars.EVENT)
    feeds = await published(schema, calendars.FEED)
    assert len(events) == before + 1
    changed = events[-1]
    assert (changed["uid"], changed["title"]) == ("fiesta@pruebas", "Fiesta cambiada")
    assert feeds[-1]["events"]["fiesta@pruebas"] == changed["fingerprint"]
    assert feeds[0]["events"]["fiesta@pruebas"] != changed["fingerprint"]


async def test_a_failing_pass_never_empties_a_calendar(api, schema, kernel, source, served):
    connection = await subscribe(api)
    await pass_of(connection, source, kernel)

    served.status = 404
    outcome = await pass_of(connection, source, kernel)

    assert outcome.outcome == "error"
    assert "ya no da el calendario" in (outcome.detail or "")
    assert len(await published(schema, calendars.FEED)) == 1


async def test_what_is_not_an_address_is_refused_on_connecting(api) -> None:
    response = await api.post(
        "/connections", json={"provider": "ical", "settings": {"url": "no es una dirección"}}
    )
    assert response.status_code == 422


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "planner"},
    )


PLANNER = {
    "name": "Planner",
    "ui": {"view": "/planner"},
    "inlets": [
        {
            "id": "calendar",
            "title": "Calendario",
            "contracts": ["calendar.event", "calendar.feed"],
            "settings": [
                {"key": "name", "kind": "text", "label": "Nombre"},
                {"key": "tone", "kind": "tone", "label": "Color"},
            ],
        }
    ],
}


@pytest.fixture
async def hub(monkeypatch, kernel):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    async with kernel_db.engine().begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values ('planner', '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest, enabled = true"
            ),
            {"manifest": json.dumps(PLANNER)},
        )
    yield
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.modules where id = 'planner'"))


async def test_an_app_subscribes_with_parameters_and_no_credential(api, schema, hub) -> None:
    answer = await ask(
        api,
        "sources.plug",
        {
            "provider": "holidays",
            "label": "Festivos · Navarra",
            "params": {"country": "es", "region": "ES-NC"},
        },
    )

    assert answer.status_code == 200, answer.text
    created = answer.json()["connection"]
    listed = (await api.get("/connections")).json()
    [found] = [c for c in listed if c["id"] == created]
    assert (found["provider"], found["label"], found["category"]) == (
        "holidays",
        "Festivos · Navarra",
        "calendar",
    )
    assert found["state"] == "active"
    ficha = (await api.get(f"/connections/{created}")).json()
    assert ficha["settings"] == {"country": "ES", "region": "ES-NC"}


async def test_a_subscription_with_parameters_that_make_no_sense_is_refused(api, hub) -> None:
    answer = await ask(
        api, "sources.plug", {"provider": "ical", "label": "X", "params": {"url": "nada"}}
    )
    assert answer.status_code == 422
    assert "https://" in answer.json()["detail"]


async def test_a_private_calendar_is_not_subscribed_from_an_app(api, hub) -> None:
    answer = await ask(
        api,
        "sources.plug",
        {"provider": "ical_private", "label": "X", "params": {"url": "https://example.org/a"}},
    )
    assert answer.status_code == 422


async def test_the_menu_says_what_can_be_subscribed_and_what_each_thing_asks(api, hub) -> None:
    answer = await ask(api, "sources.catalogue", {})

    assert answer.status_code == 200, answer.text
    sources = {one["provider"]: one for one in answer.json()["sources"]}
    assert set(sources) == {"holidays", "formula1", "football", "ical"}
    football = sources["football"]
    assert football["many"] is True
    [team] = football["asks"]
    assert (team["kind"], team["source"]) == ("lookup", "teams")
    assert sources["formula1"]["many"] is False
    assert [one["value"] for one in sources["formula1"]["asks"][0]["choices"]][:2] == [
        "race",
        "qualifying",
    ]


async def test_unsubscribing_removes_the_connection_and_says_so_in_the_log(
    api, schema, hub
) -> None:
    created = (
        await ask(
            api,
            "sources.plug",
            {"provider": "formula1", "label": "Fórmula 1", "params": {"sessions": ["race"]}},
        )
    ).json()["connection"]

    answer = await ask(api, "sources.unplug", {"connection": created})
    again = await ask(api, "sources.unplug", {"connection": created})

    assert answer.json() == {"removed": True}
    assert again.json() == {"removed": False}
    assert created not in [one["id"] for one in (await api.get("/connections")).json()]
    states = [
        event
        for event in await published(schema, "hub.connection")
        if event["connection"] == created
    ]
    assert states[-1]["removed"] is True


async def test_only_a_calendar_is_unsubscribed_from_an_app(api, hub) -> None:
    other = (
        await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "x"}})
    ).json()["id"]

    answer = await ask(api, "sources.unplug", {"connection": other})

    assert answer.status_code in (409, 422)
    assert other in [one["id"] for one in (await api.get("/connections")).json()]
