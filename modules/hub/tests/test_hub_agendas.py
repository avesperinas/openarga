from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from arga_contracts import sources
from hub import catalogue, sync
from hub.providers import agendas

TODAY = date(2026, 10, 2)
KEY = "sk-ant-" + "de-prueba-" * 3

PAGE = """
<html><head><title>Agenda · Auditorio Sintético</title><script>var x = "no";</script></head>
<body>
<nav><a href="/">Inicio</a> <a href="/entradas">Entradas</a></nav>
<ul>
  <li><a href="/evento/orquesta">Orquesta Sintética</a> Sala | sáb 3 de octubre | 19:30</li>
  <li><a href="/evento/croqueta">Semana de la Croqueta Inventada</a> del 2 al 11 oct · 90 bares</li>
  <li><a href="https://otra.example/expo">Paisajes de mentira</a> 25/09/2026 - 31/10/2026</li>
</ul>
</body></html>
"""
URL = "https://agenda.example/es/agenda"


def said(*events: dict) -> dict:
    return {
        "content": [{"type": "tool_use", "name": "events", "input": {"events": list(events)}}],
        "stop_reason": "tool_use",
    }


ORCHESTRA = {
    "title": "Orquesta Sintética",
    "starts_on": "2026-10-03",
    "ends_on": "2026-10-03",
    "time": "19:30",
    "venue": "Sala principal",
    "town": "Pamplona",
    "category": "stage",
    "summary": "Concierto.",
    "link": 3,
}
CROQUETA = {
    "title": "Semana de la Croqueta Inventada",
    "starts_on": "2026-10-02",
    "ends_on": "2026-10-11",
    "category": "eat",
    "link": 4,
    "recurring": True,
}
EXPO = {
    "title": "Paisajes de mentira",
    "starts_on": "2026-09-25",
    "ends_on": "2026-10-31",
    "category": "culture",
    "link": 5,
}


def page() -> agendas.Read:
    return agendas.parse(URL, "Auditorio Sintético", PAGE)


def test_the_page_is_its_text_with_numbered_links_and_no_scripts() -> None:
    read = page()

    assert "var x" not in read.text
    assert "Orquesta Sintética ⟨3⟩" in read.text
    assert read.links[:3] == [
        "https://agenda.example/",
        "https://agenda.example/entradas",
        "https://agenda.example/evento/orquesta",
    ]
    assert read.links[4] == "https://otra.example/expo"


@pytest.mark.parametrize(
    ("day", "written"),
    [
        (date(2026, 10, 3), "sabado 3 de octubre"),
        (date(2026, 10, 2), "del 2 al 11 oct"),
        (date(2026, 10, 11), "del 2 al 11 oct"),
        (date(2026, 10, 3), "oct 3 4815 euskadiko"),
        (date(2026, 10, 9), "oct 8 9 quien teme"),
        (date(2026, 9, 25), "25 09 2026 31 10 2026"),
        (date(2026, 10, 31), "25 09 2026 31 10 2026"),
        (date(2026, 10, 4), "2026 10 04"),
        (date(2026, 10, 2), "2 eta 4 urria"),
    ],
)
def test_a_day_is_found_however_the_agenda_writes_it(day: date, written: str) -> None:
    assert agendas.date_in(day, agendas.fold(written))


@pytest.mark.parametrize(
    ("day", "written"),
    [
        (date(2026, 10, 3), "13 de octubre"),
        (date(2026, 10, 3), "3 de noviembre"),
        (date(2026, 10, 3), ""),
    ],
)
def test_a_day_that_is_not_written_is_not_found(day: date, written: str) -> None:
    assert not agendas.date_in(day, agendas.fold(written))


def test_what_is_on_the_page_goes_in_with_its_link() -> None:
    checked = agendas.check([ORCHESTRA, CROQUETA, EXPO], page(), "c1", TODAY)

    assert checked.discarded == {}
    by_title = {event["title"]: event for event in checked.events}
    orchestra = by_title["Orquesta Sintética"]
    assert orchestra["link"] == "https://agenda.example/evento/orquesta"
    assert orchestra["time"] == "19:30" and orchestra["category"] == "stage"
    assert orchestra["source_page"] == URL and orchestra["source_name"] == "Auditorio Sintético"
    assert by_title["Semana de la Croqueta Inventada"]["recurring"] is True
    for event in checked.events:
        sources.check("leisure.event", event)


@pytest.mark.parametrize(
    ("invented", "reason"),
    [
        ({**ORCHESTRA, "title": "Concierto que no existe"}, "el título no está en la página"),
        ({**ORCHESTRA, "starts_on": "2026-10-05", "ends_on": "2026-10-05"}, "la fecha no está"),
        ({**ORCHESTRA, "link": 99}, "enlace que no es de la página"),
        ({**ORCHESTRA, "category": "concierto"}, "categoría que no existe"),
        ({**EXPO, "starts_on": "2025-09-25", "ends_on": "2025-10-31"}, "la fecha no está"),
    ],
)
def test_what_the_model_invents_does_not_go_in_and_is_counted(invented: dict, reason: str) -> None:
    checked = agendas.check([invented, CROQUETA], page(), "c1", TODAY)

    assert [event["title"] for event in checked.events] == ["Semana de la Croqueta Inventada"]
    assert any(said.startswith(reason) for said in checked.discarded)


def test_a_past_event_is_out_even_if_it_is_on_the_page() -> None:
    late = date(2026, 11, 5)

    checked = agendas.check([ORCHESTRA], page(), "c1", late)

    assert checked.events == [] and checked.discarded == {"fuera de fechas": 1}


def test_the_same_event_twice_is_one_and_its_identity_does_not_depend_on_the_summary() -> None:
    first = agendas.check([ORCHESTRA, {**ORCHESTRA, "summary": "Otra."}], page(), "c1", TODAY)
    again = agendas.check([{**ORCHESTRA, "summary": "Otra."}], page(), "c1", TODAY)

    assert len(first.events) == 1
    assert first.events[0]["key"] == again.events[0]["key"]
    assert first.events[0]["fingerprint"] != again.events[0]["fingerprint"]


def test_the_settings_are_the_chosen_pages_or_a_pasted_one() -> None:
    chosen = agendas.clean_settings({"pages": ["baluarte", "turismo"]})
    pasted = agendas.clean_settings({"url": "https://www.teatro.example/agenda"})

    assert [page["name"] for page in chosen["pages"]] == ["Baluarte", "Turismo de Navarra"]
    assert pasted["pages"] == [
        {"url": "https://www.teatro.example/agenda", "name": "teatro.example"}
    ]
    with pytest.raises(ValueError):
        agendas.clean_settings({"pages": []})
    with pytest.raises(ValueError):
        agendas.clean_settings({"url": "ftp://algo"})


def test_the_key_is_an_anthropic_key() -> None:
    assert agendas.normalise("api_key", f"  {KEY} ") == KEY
    with pytest.raises(ValueError, match="sk-ant-"):
        agendas.normalise("api_key", "otra-cosa")


def test_it_is_in_the_catalogue_as_leisure_and_offered() -> None:
    provider = catalogue.provider("agendas")

    assert provider.category == "leisure" and provider.emits == ("leisure.event",)
    assert provider.offer is not None and provider.shared == ("api_key",)
    assert "leisure" in {group.id for group in catalogue.GROUPS}


class Web:
    def __init__(self) -> None:
        self.pages = {URL: PAGE}
        self.answers: list[dict] = [said(ORCHESTRA, CROQUETA)]
        self.model_calls: list[dict] = []
        self.down: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == agendas.MESSAGES:
            body = json.loads(request.content)
            self.model_calls.append(body)
            assert request.headers["x-api-key"] == KEY
            return httpx.Response(
                200, json=self.answers[min(len(self.answers), len(self.model_calls)) - 1]
            )
        if url in self.down:
            return httpx.Response(503)
        if url in self.pages:
            return httpx.Response(200, html=self.pages[url])
        return httpx.Response(404)


@pytest.fixture
def web(monkeypatch) -> Web:
    monkeypatch.setattr(agendas, "MIN_INTERVAL", 0.0)
    monkeypatch.setattr(agendas, "today", lambda: TODAY)
    return Web()


def target(config: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("00000000-0000-4000-8000-0000000a6e4d"),
        provider="agendas",
        label="Agenda",
        config=config,
    )


async def test_a_page_that_has_not_changed_does_not_call_the_model(web) -> None:
    config = {"pages": [{"url": URL, "name": "Auditorio Sintético"}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as client:
        first = await agendas.sync(client, {"api_key": KEY}, target(config))
        again = await agendas.sync(client, {"api_key": KEY}, target({**config, **first.state}))

    assert len(web.model_calls) == 1
    assert [event["payload"]["title"] for event in first.events] == [
        "Orquesta Sintética",
        "Semana de la Croqueta Inventada",
    ]
    assert again.events == [] and again.problem is None
    assert "1 sin cambios" in again.note
    content = web.model_calls[0]["messages"][0]["content"]
    assert "Orquesta Sintética ⟨3⟩" in content and "Hoy es 2026-10-02" in content
    assert web.model_calls[0]["tool_choice"] == {"type": "tool", "name": "events"}


async def test_the_daily_budget_stops_the_pass_and_says_so(web) -> None:
    other = "https://agenda.example/otra"
    web.pages[other] = PAGE.replace("Sintética", "Distinta")
    config = {
        "pages": [{"url": URL, "name": "Una"}, {"url": other, "name": "Otra"}],
        "daily_calls": 1,
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as client:
        got = await agendas.sync(client, {"api_key": KEY}, target(config))

    assert len(web.model_calls) == 1
    assert "presupuesto" in got.problem
    assert got.state["usage"]["calls"] == 1 and list(got.state["seen"]) == [URL]


async def test_a_dead_page_does_not_lose_what_the_others_brought(web) -> None:
    dead = "https://agenda.example/caida"
    web.down.add(dead)
    config = {"pages": [{"url": dead, "name": "Caída"}, {"url": URL, "name": "Buena"}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as client:
        got = await agendas.sync(client, {"api_key": KEY}, target(config))

    assert "Caída contesta 503" in got.problem
    assert len(got.events) == 2 and URL in got.state["seen"]


async def test_a_refused_key_says_so_and_does_not_keep_trying(web) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        if str(request.url) == agendas.MESSAGES:
            web.model_calls.append({})
            return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})
        return web(request)

    other = "https://agenda.example/otra"
    web.pages[other] = PAGE
    config = {"pages": [{"url": URL, "name": "Una"}, {"url": other, "name": "Otra"}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(refused)) as client:
        got = await agendas.sync(client, {"api_key": KEY}, target(config))

    assert len(web.model_calls) == 1
    assert "no acepta la clave" in got.problem and got.state["seen"] == {}


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


async def no_wait(_: float) -> None:
    return None


async def row_of(_api, connection_id: str) -> SimpleNamespace:
    from hub.db import as_module

    async with as_module() as database:
        found = (
            await database.execute(
                text(
                    "select id, provider, label, config from hub.hub_connection "
                    "where id = cast(:id as uuid)"
                ),
                {"id": connection_id},
            )
        ).one()
    return SimpleNamespace(
        id=found.id, provider=found.provider, label=found.label, config=found.config
    )


async def test_without_the_key_nothing_is_called_and_with_it_the_log_gets_the_events(
    api, schema, kernel, web
) -> None:
    from hub import connections
    from hub.db import as_module

    async with as_module() as database:
        created = await connections.create(
            database,
            "agendas",
            "Agenda",
            {},
            from_app="outings",
            config=agendas.clean_settings({"url": URL, "name": "Auditorio"}),
        )
    connection_id = str(created)

    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as source:
        skipped = await sync.run(
            await row_of(api, connection_id), source=source, kernel=kernel, sleep=no_wait
        )
        assert skipped.outcome == "skipped" and skipped.code == "missing_credential"
        assert web.model_calls == []

        pasted = await api.put(
            f"/connections/{connection_id}/credentials/api_key", json={"value": KEY}
        )
        assert pasted.status_code == 200, pasted.text
        first = await sync.run(
            await row_of(api, connection_id), source=source, kernel=kernel, sleep=no_wait
        )
        again = await sync.run(
            await row_of(api, connection_id), source=source, kernel=kernel, sleep=no_wait
        )

    assert first.outcome == "ok", first.detail
    assert first.emitted == 2 and again.emitted == 0
    assert len(web.model_calls) == 1, "la segunda pasada vio la página igual y no llamó al modelo"
    async with schema.connect() as connection:
        titles = (
            (
                await connection.execute(
                    text(
                        "select payload->>'title' from kernel.events "
                        "where module = 'hub' and type = 'leisure.event' order by 1"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert titles == ["Orquesta Sintética", "Semana de la Croqueta Inventada"]


async def test_a_second_agenda_shares_the_key_pasted_in_the_first(api, schema) -> None:
    from hub import connections, credentials
    from hub.db import as_module

    first = await api.post(
        "/connections",
        json={
            "provider": "agendas",
            "label": "Una",
            "settings": {"url": URL},
            "secrets": {"api_key": KEY},
        },
    )
    assert first.status_code == 201, first.text
    async with as_module() as database:
        second = await connections.create(
            database,
            "agendas",
            "Otra",
            {},
            from_app="outings",
            config=agendas.clean_settings({"url": "https://otra.example/a"}),
        )
        copied = await connections.share(database, catalogue.provider("agendas"), second)
        found = await credentials.use(database, "agendas", second, "api_key")

    assert copied == 1 and found == KEY


FOUND = "https://prensa.example/jornadas-de-la-alcachofa"
JORNADAS = """
<html><body><article>
<h1>Jornadas Sintéticas de la Alcachofa</h1>
<p>Del 9 al 18 de octubre, quince bares de Tudela. XX edición.</p>
</article></body></html>
"""
ALCACHOFA = {
    "title": "Jornadas Sintéticas de la Alcachofa",
    "starts_on": "2026-10-09",
    "ends_on": "2026-10-18",
    "town": "Tudela",
    "category": "eat",
    "recurring": True,
}


class SearchingWeb(Web):
    def __init__(self) -> None:
        super().__init__()
        self.pages[FOUND] = JORNADAS
        self.searched: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == agendas.MESSAGES:
            body = json.loads(request.content)
            if body["tools"][0].get("type", "").startswith("web_search"):
                query = body["messages"][0]["content"]
                self.searched.append(query)
                results = (
                    [{"type": "web_search_result", "url": FOUND, "title": "Jornadas"}]
                    if "gastronómicas" in query
                    else {"type": "web_search_tool_result_error", "error_code": "unavailable"}
                )
                return httpx.Response(
                    200,
                    json={
                        "content": [
                            {"type": "server_tool_use", "name": "web_search", "input": {}},
                            {"type": "web_search_tool_result", "content": results},
                        ]
                    },
                )
            self.model_calls.append(body)
            content = body["messages"][0]["content"]
            return httpx.Response(200, json=said(ALCACHOFA) if FOUND in content else said())
        return super().__call__(request)


async def test_the_weekly_search_brings_what_no_fixed_agenda_has_with_its_page(web) -> None:
    web = SearchingWeb()
    config = {"pages": [], "search_now": True, "weekly_searches": 3}
    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as client:
        got = await agendas.sync(client, {"api_key": KEY}, target(config))

    assert len(web.searched) == 3
    assert all("Navarra octubre 2026" in query for query in web.searched)
    [event] = [one["payload"] for one in got.events]
    assert event["title"] == "Jornadas Sintéticas de la Alcachofa"
    assert event["source_page"] == FOUND and event["source_name"] == "prensa.example"
    assert event["recurring"] is True
    assert "presupuesto de búsquedas" in got.problem
    assert got.state["searches"]["count"] == 3 and got.state["searched_at"]
    assert got.state["search_now"] is False


async def test_the_search_only_runs_when_asked(web) -> None:
    web = SearchingWeb()
    long_ago = datetime.now(agendas.MADRID) - timedelta(days=30)
    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as client:
        await agendas.sync(
            client,
            {"api_key": KEY},
            target({"pages": [], "search": True, "searched_at": long_ago.isoformat()}),
        )

    assert web.searched == []


def test_what_comes_back_every_year_is_searched_near_its_month() -> None:
    found = agendas.queries(
        date(2026, 10, 2),
        [{"title": "Vinofest", "month": 4}, {"title": "Exaltación del Piquillo", "month": 11}],
    )

    assert "jornadas gastronómicas Navarra octubre 2026" in found
    assert "fiestas de los pueblos de Navarra noviembre 2026" in found
    assert "Exaltación del Piquillo 2026 fechas" in found
    assert not any("Vinofest" in query for query in found)
    assert agendas.queries(date(2026, 12, 20), [])[-1] == "ferias en Navarra enero 2027"


def test_it_is_offered_with_the_four_agendas_and_no_automatic_search() -> None:
    [pages] = catalogue.provider("agendas").offer.asks

    assert len(pages.choices) == 4 and "search" not in pages.defaults


async def test_it_remembers_what_it_published_that_comes_back_every_year(
    api, schema, kernel, web
) -> None:
    from hub import connections
    from hub.db import as_module

    async with as_module() as database:
        created = await connections.create(
            database,
            "agendas",
            "Agenda",
            {"api_key": KEY},
            from_app="outings",
            config=agendas.clean_settings({"url": URL}),
        )
    web.answers = [said({**CROQUETA, "recurring": True}, ORCHESTRA)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(web)) as source:
        first = await sync.run(
            await row_of(api, str(created)), source=source, kernel=kernel, sleep=no_wait
        )
    assert first.outcome == "ok", first.detail

    async with as_module() as database:
        recalled = await agendas.recall(database, await row_of(api, str(created)))

    assert recalled == {"recurring": [{"title": "Semana de la Croqueta Inventada", "month": 10}]}


async def test_a_page_whose_answer_does_not_fit_is_read_in_pieces(web) -> None:

    def long(request: httpx.Request) -> httpx.Response:
        if str(request.url) == agendas.MESSAGES:
            body = json.loads(request.content)
            web.model_calls.append(body)
            content = body["messages"][0]["content"]
            if "Orquesta" in content and "Croqueta" in content:
                return httpx.Response(200, json={"content": [], "stop_reason": "max_tokens"})
            return httpx.Response(
                200, json=said(ORCHESTRA) if "Orquesta" in content else said(CROQUETA)
            )
        return web(request)

    config = {"pages": [{"url": URL, "name": "Larga"}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(long)) as client:
        got = await agendas.sync(client, {"api_key": KEY}, target(config))

    assert len(web.model_calls) == 3
    assert {one["payload"]["title"] for one in got.events} == {
        "Orquesta Sintética",
        "Semana de la Croqueta Inventada",
    }
    assert URL in got.state["seen"] and got.problem is None


async def test_a_page_that_never_fits_is_not_marked_as_read(web) -> None:
    def never(request: httpx.Request) -> httpx.Response:
        if str(request.url) == agendas.MESSAGES:
            web.model_calls.append({})
            return httpx.Response(200, json={"content": [], "stop_reason": "max_tokens"})
        return web(request)

    config = {"pages": [{"url": URL, "name": "Larga"}], "daily_calls": 50}
    async with httpx.AsyncClient(transport=httpx.MockTransport(never)) as client:
        got = await agendas.sync(client, {"api_key": KEY}, target(config))

    assert got.state["seen"] == {}
    assert "no cabe" in got.problem and "0 leída(s)" in got.problem


async def test_it_asks_for_html_like_a_browser(web) -> None:
    asked: list[httpx.Request] = []

    def keep(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return web(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(keep)) as client:
        await agendas.download(client, URL, "Una")

    assert asked[0].headers["accept"].startswith("text/html")
