from __future__ import annotations

import json
import secrets
from uuid import UUID

import pytest
from httpx import ASGITransport
from sqlalchemy import text

from arga_contracts import sources
from hub import capabilities, catalogue, finance, plugs, sync

TOKEN = secrets.token_hex(16)
CALENDAR = {
    "id": "calendar",
    "title": "Calendario",
    "contracts": ["calendar.event", "calendar.feed"],
    "settings": [
        {"key": "name", "kind": "text", "label": "Nombre"},
        {"key": "tone", "kind": "tone", "label": "Color"},
    ],
}
MANIFEST = {
    "name": "Planner",
    "database": {"schema": "planner", "role": "mod_planner"},
    "api": {"prefix": "/api/planner"},
    "ui": {"view": "/planner"},
    "inlets": [CALENDAR],
}


def test_every_source_produces_only_known_contracts() -> None:
    for provider in catalogue.PROVIDERS:
        unknown = set(provider.emits) - sources.SOURCE_CONTRACTS
        assert not unknown, f"{provider.id} produce {unknown}, que no son contratos"


def test_every_question_that_searches_has_a_search() -> None:
    for provider in catalogue.offered():
        assert provider.offer is not None
        for ask in provider.offer.asks:
            if ask.kind in ("lookup", "pick") and not ask.choices:
                assert provider.search_for(ask.key), f"{provider.id}.{ask.key} no busca nada"


def test_every_offer_goes_in_a_group_the_menu_knows() -> None:
    groups = {group.id for group in catalogue.GROUPS}
    for provider in catalogue.offered():
        assert provider.offer is not None and provider.offer.group in groups, provider.id


SECRET_AFTER_PLUG = {"agendas"}


def test_nothing_offered_asks_for_a_secret() -> None:
    for provider in catalogue.offered():
        secrets = {secret.key for secret in provider.secrets}
        assert not secrets & {ask.key for ask in provider.offer.asks}, provider.id
        assert not secrets or provider.id in SECRET_AFTER_PLUG, provider.id


class Kernel:
    def __init__(self) -> None:
        self.posted: list[dict] = []

    async def post(self, path: str, json: dict, headers: dict) -> object:
        self.posted.append(json)
        return type(
            "R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"created": True}}
        )()


MOVEMENT = {
    "ts": "2026-10-01T00:00:00+00:00",
    "type": "finance.movement",
    "payload": {
        "account": "a",
        "reference": "r",
        "booked_on": "2026-10-01",
        "amount": "-1.00",
        "currency": "EUR",
    },
    "dedup_hash": "m:1",
}


async def test_a_pass_with_one_event_out_of_its_contract_publishes_nothing() -> None:
    kernel = Kernel()
    broken = {**MOVEMENT, "payload": {**MOVEMENT["payload"], "amount": "uno"}, "dedup_hash": "m:2"}
    result = sync.Outcome(UUID(int=0), "ok")

    with pytest.raises(sources.BadSource, match="amount"):
        await sync.publish_all(kernel, "enable_banking", [MOVEMENT, broken], result)  # type: ignore[arg-type]

    assert kernel.posted == []


async def test_a_source_publishes_only_what_its_sheet_says_it_produces() -> None:
    kernel = Kernel()
    result = sync.Outcome(UUID(int=0), "ok")

    with pytest.raises(sources.BadSource, match="no declara"):
        await sync.publish_all(kernel, "ine", [MOVEMENT], result)  # type: ignore[arg-type]

    assert kernel.posted == []


def movement(description: str) -> dict:
    return {**MOVEMENT, "payload": {**MOVEMENT["payload"], "description": description}}


def test_the_hub_reads_the_merchant_and_the_bank_category_from_the_text() -> None:
    [found] = finance.enrich(
        [movement("PAGO CON TARJETA EN TIENDA DE PRUEBA // PAGO CON TARJETA // Tienda Prueba  12")],
        "BBVA",
    )
    assert found["payload"]["merchant"] == "Tienda Prueba"
    assert found["payload"]["bank_category"] == "TIENDA DE PRUEBA"
    assert found["dedup_hash"] == MOVEMENT["dedup_hash"]
    sources.check("finance.movement", found["payload"])


def test_an_own_transfer_is_said_and_a_bank_is_known_by_its_alias() -> None:
    [own] = finance.enrich([movement("TRASPASO // TRASPASO A CUENTA 1234")], "bbva")
    [alias] = finance.enrich([movement("TJ-Comercio de prueba")], "Caja Rural de Navarra")
    assert own["payload"]["own_transfer"] is True
    assert alias["payload"]["merchant"] == "Comercio de prueba"


def test_a_bank_without_rules_is_left_as_it_came() -> None:
    events = [movement("Algo sin reglas")]
    assert finance.enrich(events, "Banco de Prueba") == events


def ask(api, capability: str, body: dict, module: str = "planner"):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": module},
    )


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
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values ('planner', '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest, enabled = true"
            ),
            {"manifest": json.dumps(MANIFEST)},
        )
    yield ASGITransport(app=kernel_app)
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))
        await connection.execute(text("delete from kernel.modules where id = 'planner'"))
    await kernel_db.engine().dispose()


@pytest.fixture
def hub(monkeypatch, kernel):
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "kernel_transport", lambda: kernel)


async def connection_events(schema) -> list[dict]:
    async with schema.connect() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "select payload from kernel.events where module = 'hub' "
                        "and type = 'hub.connection' order by ts, ingested_at"
                    )
                )
            )
            .scalars()
            .all()
        )


async def test_an_app_learns_what_plugs_into_its_inlets_without_naming_a_source(api, hub) -> None:
    answer = await ask(api, "sources.catalogue", {})

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert [inlet["key"] for inlet in body["inlets"]] == ["planner.calendar"]
    assert {group["id"] for group in body["groups"]} >= {"sport", "holidays", "other"}
    offered = {one["provider"]: one for one in body["sources"]}
    assert set(offered) == {"holidays", "formula1", "football", "ical"}
    football = offered["football"]
    assert football["produces"] == ["calendar.event", "calendar.feed"]
    assert [inlet["key"] for inlet in football["inlets"]] == ["planner.calendar"]
    assert [s["key"] for s in football["inlets"][0]["settings"]] == ["name", "tone"]


async def test_an_app_without_inlets_is_offered_nothing(api, hub) -> None:
    answer = await ask(api, "sources.catalogue", {}, module="library")
    assert answer.status_code == 200
    assert answer.json()["sources"] == []


async def test_an_app_plugs_a_source_with_what_its_inlet_asks(api, schema, hub) -> None:
    answer = await ask(
        api,
        "sources.plug",
        {
            "provider": "formula1",
            "label": "Fórmula 1",
            "params": {"sessions": ["race"]},
            "settings": {"name": "La F1", "tone": 3, "invented": "no"},
        },
    )

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["inlet"] == "planner.calendar"
    assert body["settings"] == {"name": "La F1", "tone": 3}
    ficha = (await api.get(f"/connections/{body['connection']}")).json()
    assert ficha["plugs"] == {"planner.calendar": {"name": "La F1", "tone": 3}}
    [told] = await connection_events(schema)
    assert told["plugs"] == {"planner.calendar": {"name": "La F1", "tone": 3}}
    assert told["produces"] == ["calendar.event", "calendar.feed"]


async def test_plugging_the_same_source_twice_gives_back_the_one_there_is(api, schema, hub) -> None:
    body = {"provider": "formula1", "label": "F1", "params": {"sessions": ["race"]}}
    first = (await ask(api, "sources.plug", body)).json()
    again = (await ask(api, "sources.plug", body)).json()
    params = {"sessions": ["race", "qualifying"]}
    other = (await ask(api, "sources.plug", {**body, "params": params})).json()

    assert first["existing"] is False
    assert again["existing"] is True
    assert again["connection"] == first["connection"]
    assert other["existing"] is False and other["connection"] != first["connection"]
    assert len(await connection_events(schema)) == 2


async def test_a_tone_out_of_the_palette_is_refused(api, hub) -> None:
    answer = await ask(
        api,
        "sources.plug",
        {"provider": "formula1", "label": "F1", "settings": {"tone": 99}},
    )
    assert answer.status_code == 422


async def test_what_does_not_enter_any_inlet_of_the_app_is_not_plugged_from_it(api, hub) -> None:
    answer = await ask(
        api,
        "sources.plug",
        {"provider": "formula1", "label": "F1", "params": {"sessions": ["race"]}},
        module="library",
    )
    assert answer.status_code == 409


async def test_an_app_searches_what_a_source_asks(api, hub, monkeypatch) -> None:
    async def teams(_client, query, _parent):
        return [{"code": "1", "name": f"Equipo {query}"}]

    provider = catalogue.BY_ID["football"]
    monkeypatch.setitem(provider.searches, "teams", teams)

    answer = await ask(
        api, "sources.search", {"provider": "football", "ask": "team", "query": "Prueba"}
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["results"] == [{"code": "1", "name": "Equipo Prueba"}]


async def test_a_question_that_does_not_search_says_so(api, hub) -> None:
    answer = await ask(api, "sources.search", {"provider": "formula1", "ask": "sessions"})
    assert answer.status_code == 422


async def test_an_app_unplugs_what_enters_its_inlets(api, schema, hub) -> None:
    created = (
        await ask(
            api,
            "sources.plug",
            {"provider": "formula1", "label": "F1", "params": {"sessions": ["race"]}},
        )
    ).json()["connection"]

    answer = await ask(api, "sources.unplug", {"connection": created})

    assert answer.json() == {"removed": True}
    assert (await api.get(f"/connections/{created}")).status_code == 404
    assert (await connection_events(schema))[-1]["removed"] is True


async def test_an_app_does_not_unplug_what_does_not_enter_its_inlets(api, hub) -> None:
    created = (
        await ask(
            api,
            "sources.plug",
            {"provider": "formula1", "label": "F1", "params": {"sessions": ["race"]}},
        )
    ).json()["connection"]

    answer = await ask(api, "sources.unplug", {"connection": created}, module="library")

    assert answer.status_code == 422
    assert (await api.get(f"/connections/{created}")).status_code == 200


async def test_the_catalogue_says_where_each_source_lands(api, hub) -> None:
    listed = {
        item["id"]: item
        for category in (await api.get("/catalogue")).json()
        for item in category["providers"]
    }
    assert [inlet["key"] for inlet in listed["ical"]["inlets"]] == ["planner.calendar"]
    assert listed["ical"]["offer"]["asks"][0]["key"] == "url"
    assert listed["ical_private"]["offer"] is None
    assert listed["enable_banking"]["inlets"] == []


async def test_plugging_in_hub_answers_each_inlet(api, schema, hub) -> None:
    response = await api.post(
        "/connections",
        json={
            "provider": "ical",
            "label": "Pruebas",
            "settings": {"url": "https://example.org/a.ics"},
            "plugs": {"planner.calendar": {"tone": 5}, "otra.toma": {"name": "no"}},
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["plugs"] == {"planner.calendar": {"name": "Pruebas", "tone": 5}}
    [told] = await connection_events(schema)
    assert told["plugs"] == {"planner.calendar": {"name": "Pruebas", "tone": 5}}


async def test_without_the_kernel_a_source_still_connects_without_inlet_settings(
    api, monkeypatch
) -> None:
    async def nowhere(_transport=None):
        return []

    monkeypatch.setattr(plugs, "inlets", nowhere)
    response = await api.post(
        "/connections",
        json={"provider": "ical", "settings": {"url": "https://example.org/b.ics"}},
    )
    assert response.status_code == 201, response.text
    assert response.json()["plugs"] == {}


def test_every_capability_but_the_generic_ones_is_served_by_a_source() -> None:
    from hub import apps

    generic = {name for name in capabilities.CAPABILITIES if name.startswith(("sources.", "ai."))}
    for name in set(capabilities.CAPABILITIES) - generic:
        assert apps.serving(name), f"ninguna fuente sirve {name}"
    for provider in catalogue.PROVIDERS:
        assert set(provider.serves) <= set(capabilities.CAPABILITIES), provider.id


def test_each_app_gets_what_reaches_its_inlets_and_what_serves_what_it_asks() -> None:
    from hub import apps

    installed = [
        {"id": "planner", "name": "Planner", "view": "/planner", "enabled": True, "uses": []},
        {
            "id": "library",
            "name": "Library",
            "view": "/library",
            "enabled": True,
            "uses": ["books.search"],
        },
        {"id": "nada", "name": "Nada", "view": "/nada", "enabled": True, "uses": ["agenda.move"]},
        {"id": "hub", "name": "Hub", "enabled": True, "uses": []},
    ]
    inlets = [{"key": "planner.calendar", "module": "planner", **CALENDAR}]

    found, others = apps.by_app(installed, inlets)

    assert [app["module"] for app in found] == ["library", "planner"]
    [calendar] = found[1]["inlets"]
    assert set(calendar["providers"]) == {
        "holidays",
        "formula1",
        "football",
        "ical",
        "ical_private",
    }
    assert {one["provider"] for one in found[0]["services"]} == {"openlibrary", "google_books"}
    assert "enable_banking" in others and "ical" not in others and "openlibrary" not in others


async def test_the_home_by_app_comes_from_the_manifests(api, hub) -> None:
    answer = await api.get("/apps")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    planner = next(app for app in body["apps"] if app["module"] == "planner")
    assert planner["name"] == "Planner"
    assert [inlet["key"] for inlet in planner["inlets"]] == ["planner.calendar"]
    assert "ical" in planner["inlets"][0]["providers"]
    assert "ical" not in body["others"]
