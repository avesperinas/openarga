from __future__ import annotations

import secrets

import httpx
import pytest
from sqlalchemy import text

from hub import capabilities
from hub.providers import food
from hub.providers.food import search_off

TOKEN = secrets.token_hex(16)
LEEK = {
    "foods": [
        {
            "fdcId": 11246,
            "description": "Leeks, raw",
            "foodCategory": "Vegetables and Vegetable Products",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 61},
                {"nutrientId": 1003, "value": 1.5},
                {"nutrientId": 1004, "value": 0.3},
                {"nutrientId": 1005, "value": 14.15},
                {"nutrientId": 1089, "value": 2.1},
                {"nutrientId": 1190, "value": 64},
            ],
        }
    ]
}
LEEK_DETAIL = [
    {
        "fdcId": 11246,
        "description": "Leeks, raw",
        "foodCategory": {"description": "Vegetables and Vegetable Products"},
        "foodNutrients": [
            {"nutrient": {"id": 1008}, "amount": 61},
            {"nutrient": {"id": 1003}, "amount": 1.5},
            {"nutrient": {"id": 1004}, "amount": 0.3},
            {"nutrient": {"id": 1005}, "amount": 14.15},
            {"nutrient": {"id": 1089}, "amount": 2.1},
            {"nutrient": {"id": 1093}, "amount": 20},
        ],
    }
]
YOGURT = {
    "product": {
        "code": "8400000000017",
        "product_name": "Yogur natural",
        "nutriments": {
            "energy-kcal_100g": 60,
            "proteins_100g": 3.5,
            "fat_100g": 3.1,
            "carbohydrates_100g": 4.5,
            "calcium_100g": 0.12,
        },
    }
}


class Sources:
    def __init__(self) -> None:
        self.usda_down = False
        self.usda_errors: list[int] = []
        self.usda_reply: dict | None = None
        self.off_hits: list[dict] = []
        self.keys: list[str] = []
        self.off: list[httpx.URL] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "nal.usda.gov" in request.url.host:
            self.keys.append(request.url.params["api_key"])
            if self.usda_down:
                raise httpx.ConnectError("sin red", request=request)
            if self.usda_errors:
                return httpx.Response(self.usda_errors.pop(0))
            if request.method == "POST":
                return httpx.Response(200, json=LEEK_DETAIL)
            return httpx.Response(200, json=self.usda_reply or LEEK)
        self.off.append(request.url)
        if "/api/v2/product/" in request.url.path:
            return httpx.Response(200, json=YOGURT)
        return httpx.Response(200, json={"hits": self.off_hits})


@pytest.fixture
def sources(monkeypatch) -> Sources:
    fake = Sources()
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", TOKEN)
    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setenv("FOOD_SOURCE_BACKOFF_SECONDS", "0")
    food.forget()
    return fake


def ask(api, capability: str, body: dict):
    return api.post(
        f"/capabilities/{capability}",
        json=body,
        headers={"x-module-token": TOKEN, "x-arga-module": "recipes"},
    )


async def by_provider(api) -> dict:
    return {c["provider"]: c for c in (await api.get("/connections")).json()}


async def logged(schema) -> int:
    async with schema.connect() as connection:
        return await connection.scalar(
            text("select count(*) from kernel.events where module = 'hub'")
        )


async def test_a_search_brings_candidates_and_leaves_nothing_in_the_log(api, schema, sources):
    await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "clave-1"}})
    before = await logged(schema)

    answer = (await ask(api, "food.search", {"query": "leek"})).json()

    assert answer["failed"] == []
    [leek] = answer["candidates"]
    assert (leek["source"], leek["source_ref"], leek["kcal_100g"]) == ("usda", "11246", 61.0)
    assert sources.keys == ["clave-1"]
    connected = await by_provider(api)
    assert set(connected) == {"usda", "openfoodfacts"}
    ficha = (await api.get(f"/connections/{connected['usda']['id']}")).json()
    assert [(r["operation"], r["outcome"]) for r in ficha["runs"]] == [("search", "ok")]
    assert await logged(schema) == before


async def test_open_food_facts_is_asked_by_its_search_service(api, sources) -> None:
    await ask(api, "food.search", {"query": "yogur"})

    [url] = sources.off
    assert (url.host, url.path) == ("search.openfoodfacts.org", "/search")
    assert (url.params["q"], url.params["langs"]) == ("yogur", "es")


async def test_without_the_usda_key_it_says_so(api, sources) -> None:
    answer = (await ask(api, "food.search", {"query": "leek"})).json()

    assert answer["failed"] == [{"source": "usda", "reason": "sin clave de USDA: ponla en Hub"}]
    assert sources.keys == []


async def test_a_paused_source_is_not_asked(api, sources) -> None:
    created = await api.post(
        "/connections", json={"provider": "usda", "secrets": {"api_key": "k1"}}
    )
    await api.post(f"/connections/{created.json()['id']}/pause")

    answer = (await ask(api, "food.search", {"query": "leek"})).json()

    assert answer["failed"] == [{"source": "usda", "reason": "USDA está en pausa en Hub"}]
    assert sources.keys == []


async def test_a_source_that_is_down_is_seen_in_hub(api, sources) -> None:
    await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "clave-1"}})
    sources.usda_down = True

    answers = [(await ask(api, "food.search", {"query": "leek"})).json() for _ in range(2)]

    assert answers[0]["failed"] == [{"source": "usda", "reason": "USDA no contestó: ConnectError"}]
    usda = (await by_provider(api))["usda"]
    assert usda["state"] == "failing"
    assert "USDA no contestó" in usda["reason"]


async def test_the_usda_key_from_an_app_passes_once_and_overwrites_nothing(api, sources) -> None:
    first = await ask(api, "usda.handoff", {"secrets": {"api_key": "del-servidor"}})
    again = await ask(api, "usda.handoff", {"secrets": {"api_key": "otra"}})

    assert first.json()["created"] is True
    assert again.json() == {"connection": first.json()["connection"], "created": False}
    await ask(api, "food.search", {"query": "leek"})
    assert sources.keys == ["del-servidor"]


def _off(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_product_with_its_energy_only_in_kilojoules_is_still_a_food() -> None:
    milk = {
        "code": "0000000000017",
        "product_name": "Leche sintética",
        "brands": ["Marca Sintética"],
        "nutriments": {
            "energy-kj_100g": 278,
            "proteins_100g": 2.2,
            "fat_100g": 3,
            "carbohydrates_100g": 5.52,
        },
    }
    async with _off(lambda request: httpx.Response(200, json={"hits": [milk]})) as client:
        [found] = await search_off(client, "leche")

    assert found.kcal_100g == 66.4


async def test_a_product_brings_its_package_and_serving_in_grams() -> None:
    yogurt = {
        "code": "0000000000024",
        "product_name": "Yogur sintético",
        "nutriments": {
            "energy-kcal_100g": 61,
            "proteins_100g": 3.5,
            "fat_100g": 3.3,
            "carbohydrates_100g": 4.7,
        },
        "product_quantity": "125",
        "product_quantity_unit": "g",
        "serving_quantity": 125,
    }
    juice = {
        **yogurt,
        "code": "0000000000031",
        "product_name": "Zumo sintético",
        "product_quantity": 1000,
        "product_quantity_unit": "ml",
        "serving_quantity": "200",
        "serving_quantity_unit": "g",
    }
    async with _off(lambda request: httpx.Response(200, json={"hits": [yogurt, juice]})) as client:
        first, second = await search_off(client, "sintético")

    assert first.portions == [{"name": "envase", "grams": 125.0}]
    assert second.portions == [{"name": "ración", "grams": 200.0}]


def test_usda_brings_a_serving_from_its_measures() -> None:
    from hub.providers.food import _usda_portions

    assert _usda_portions({"servingSize": 30, "servingSizeUnit": "g"}) == [
        {"name": "ración", "grams": 30.0}
    ]
    assert _usda_portions(
        {"foodPortions": [{"amount": 0.5, "gramWeight": 60}, {"amount": 1, "gramWeight": 245}]}
    ) == [{"name": "ración", "grams": 245.0}]
    assert _usda_portions({"foodPortions": []}) == []


async def test_a_barcode_open_food_facts_does_not_have_is_not_a_failure() -> None:
    async with _off(lambda request: httpx.Response(404, json={"status": 0})) as client:
        assert await search_off(client, "0000000000017") == []


async def test_a_candidate_brings_every_nutrient_its_source_has(api, sources) -> None:
    await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "clave-1"}})

    [leek] = (await ask(api, "food.search", {"query": "leek"})).json()["candidates"]

    assert leek["nutrients"] == {
        "kcal": 61,
        "protein": 1.5,
        "fat": 0.3,
        "carbs": 14.15,
        "iron": 2.1,
        "folate": 64,
    }


async def test_food_get_brings_chosen_foods_again_whole_from_each_source(api, sources) -> None:
    await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "clave-1"}})
    await ask(api, "food.search", {"query": "leek"})

    answer = (
        await ask(
            api,
            "food.get",
            {
                "items": [
                    {"source": "usda", "source_ref": "11246"},
                    {"source": "off", "source_ref": "8400000000017"},
                ]
            },
        )
    ).json()

    assert answer["failed"] == []
    leek, yogurt = answer["candidates"]
    assert (leek["source_ref"], leek["nutrients"]["iron"], leek["salt_100g"]) == (
        "11246",
        2.1,
        0.05,
    )
    assert (yogurt["source_ref"], yogurt["nutrients"]["calcium"]) == ("8400000000017", 120)


async def test_food_get_without_the_usda_key_says_so_and_brings_the_rest(api, sources) -> None:
    await ask(api, "food.search", {"query": "yogur"})

    answer = (
        await ask(
            api,
            "food.get",
            {
                "items": [
                    {"source": "usda", "source_ref": "11246"},
                    {"source": "off", "source_ref": "8400000000017"},
                ]
            },
        )
    ).json()

    assert [one["source"] for one in answer["failed"]] == ["usda"]
    assert [one["source_ref"] for one in answer["candidates"]] == ["8400000000017"]


def _candidate(**overrides) -> food.Candidate:
    values = {
        "source": "off",
        "source_ref": "0000000000017",
        "name": "Sintético",
        "kcal_100g": 100.0,
        "protein_100g": 5.0,
        "fat_100g": 5.0,
        "carbs_100g": 10.0,
    }
    return food.Candidate(**{**values, **overrides})


def test_pure_oil_is_a_food_and_impossible_figures_are_not() -> None:
    oil = _candidate(source="usda", name="Fish oil", kcal_100g=902, fat_100g=100, carbs_100g=0)
    salty = _candidate(name="Sal mal puesta", salt_100g=3210)
    negative = _candidate(name="Negativo", protein_100g=-1)
    heavy = _candidate(name="Pesado", protein_100g=60, fat_100g=40, carbs_100g=40)

    kept, dropped = food.sieve([oil, salty, negative, heavy])

    assert kept == [oil]
    assert [(one["name"], one["reason"]) for one in dropped] == [
        ("Sal mal puesta", "3210 g de sal por 100 g"),
        ("Negativo", "-1 g de proteína por 100 g"),
        ("Pesado", "sus macros suman más de 100 g por 100 g"),
    ]


async def test_a_search_drops_impossible_candidates_and_says_which(api, sources) -> None:
    salty = {
        "code": "0000000000024",
        "product_name": "Sal mal puesta",
        "nutriments": {
            "energy-kcal_100g": 40,
            "proteins_100g": 1,
            "fat_100g": 1,
            "carbohydrates_100g": 7,
            "salt_100g": 3210,
        },
    }
    sources.off_hits = [salty]

    answer = (await ask(api, "food.search", {"query": "coffee brewed"})).json()

    assert answer["candidates"] == []
    assert answer["discarded"] == [
        {"source": "off", "name": "Sal mal puesta", "reason": "3210 g de sal por 100 g"}
    ]


async def test_a_reply_that_cannot_be_read_fails_that_source_only(api, sources) -> None:
    await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "clave-1"}})
    sources.usda_reply = {"foods": 5}
    sources.off_hits = [YOGURT["product"]]

    answer = (await ask(api, "food.search", {"query": "yogur"})).json()

    assert [one["source_ref"] for one in answer["candidates"]] == ["8400000000017"]
    [failed] = answer["failed"]
    assert failed["source"] == "usda"
    assert "no se entiende" in failed["reason"]


async def test_a_server_error_is_asked_again_and_a_cached_search_is_not_a_run(api, sources) -> None:
    await api.post("/connections", json={"provider": "usda", "secrets": {"api_key": "clave-1"}})
    sources.usda_errors = [503]

    first = (await ask(api, "food.search", {"query": "leek"})).json()
    again = (await ask(api, "food.search", {"query": "LEEK"})).json()

    assert first["failed"] == [] and again["candidates"] == first["candidates"]
    assert sources.keys == ["clave-1", "clave-1"]
    usda = (await by_provider(api))["usda"]
    ficha = (await api.get(f"/connections/{usda['id']}")).json()
    assert [(r["operation"], r["outcome"]) for r in ficha["runs"]] == [("search", "ok")]


async def test_a_source_that_never_answers_gives_up_within_its_budget(monkeypatch) -> None:
    monkeypatch.setenv("FOOD_SOURCE_BACKOFF_SECONDS", "0")
    calls: list[int] = []

    def always_down(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    async with _off(always_down) as client:
        with pytest.raises(food.SourceFailed, match="HTTPStatusError"):
            await search_off(client, "leche")

    assert len(calls) == food.attempts()
