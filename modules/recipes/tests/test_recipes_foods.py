from __future__ import annotations

import httpx
import pytest

from recipes.main import app
from recipes.sources import category_hint, looks_like_barcode

USDA_LEEK = {
    "foods": [
        {
            "fdcId": 11246,
            "description": "Leeks, (bulb and lower leaf-portion), raw",
            "foodCategory": "Vegetables and Vegetable Products",
            "foodNutrients": [
                {"nutrientId": 1008, "value": 61},
                {"nutrientId": 1003, "value": 1.5},
                {"nutrientId": 1004, "value": 0.3},
                {"nutrientId": 1005, "value": 14.15},
                {"nutrientId": 1079, "value": 1.8},
                {"nutrientId": 1093, "value": 20},
            ],
        },
        {
            "fdcId": 99999,
            "description": "Leek soup, incomplete",
            "foodNutrients": [{"nutrientId": 1008, "value": 40}],
        },
    ]
}

OFF_YOGURT = {
    "hits": [
        {
            "code": "8410128750121",
            "product_name": "Yogur natural",
            "brands": ["Marca Sintética"],
            "categories": ["Lácteos", "Yogures"],
            "nutriments": {
                "energy-kcal_100g": 61,
                "proteins_100g": 3.5,
                "fat_100g": 3.2,
                "carbohydrates_100g": 4.7,
                "salt_100g": 0.12,
            },
        }
    ]
}
OFF_YOGURT_PRODUCT = {
    **OFF_YOGURT["hits"][0],
    "brands": "Marca Sintética, Otra",
    "categories": "Lácteos, Yogures",
}


def both_answer(request: httpx.Request) -> httpx.Response:
    if "nal.usda.gov" in request.url.host:
        return httpx.Response(200, json=USDA_LEEK)
    return httpx.Response(200, json=OFF_YOGURT)


@pytest.fixture
async def searching(api, hub):
    await hub.with_usda()

    def use(handler):
        hub.answer(handler)
        return api

    yield use


async def test_both_sources_end_up_in_the_same_shape(searching) -> None:
    response = await searching(both_answer).get("/foods/search", params={"q": "puerro"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["failed"] == []
    by_source = {candidate["source"]: candidate for candidate in body["candidates"]}

    leek = by_source["usda"]
    assert leek["source_ref"] == "11246"
    assert leek["macros"]["kcal"] == 61
    assert leek["macros"]["protein"] == 1.5
    assert leek["macros"]["salt"] == 0.05
    assert leek["category_hint"] == "vegetable"

    yogurt = by_source["off"]
    assert yogurt["brand"] == "Marca Sintética"
    assert yogurt["macros"]["salt"] == 0.12
    assert yogurt["category_hint"] == "dairy"


async def test_an_incomplete_nutrition_panel_is_not_offered(searching) -> None:
    body = (await searching(both_answer).get("/foods/search", params={"q": "puerro"})).json()

    assert "99999" not in [candidate["source_ref"] for candidate in body["candidates"]]


async def test_one_source_down_does_not_take_the_other_with_it(searching) -> None:
    def usda_down(request: httpx.Request) -> httpx.Response:
        if "nal.usda.gov" in request.url.host:
            raise httpx.ConnectError("sin red", request=request)
        return httpx.Response(200, json=OFF_YOGURT)

    body = (await searching(usda_down).get("/foods/search", params={"q": "yogur"})).json()

    assert [c["source"] for c in body["candidates"]] == ["off"]
    assert body["failed"] == [{"source": "usda", "reason": "USDA no contestó: ConnectError"}]


async def test_without_the_usda_key_it_says_so_instead_of_returning_less(api, hub) -> None:
    hub.answer(lambda request: httpx.Response(200, json=OFF_YOGURT))

    body = (await api.get("/foods/search", params={"q": "yogur"})).json()

    assert body["failed"][0]["source"] == "usda"
    assert "ponla en Hub" in body["failed"][0]["reason"]
    assert [c["source"] for c in body["candidates"]] == ["off"]


async def test_with_the_hub_down_both_say_so(api, monkeypatch) -> None:

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(down))

    body = (await api.get("/foods/search", params={"q": "yogur"})).json()

    assert body["candidates"] == []
    assert [f["source"] for f in body["failed"]] == ["usda", "off"]
    assert "Hub no contesta" in body["failed"][0]["reason"]


async def test_an_imported_food_stays_and_is_not_asked_for_again(searching) -> None:
    client = searching(both_answer)
    candidate = next(
        c
        for c in (await client.get("/foods/search", params={"q": "puerro"})).json()["candidates"]
        if c["source"] == "usda"
    )

    imported = await client.post(
        "/foods",
        json={
            "source": candidate["source"],
            "source_ref": candidate["source_ref"],
            "name": "Puerro",
            "category_id": "vegetable",
            "macros": candidate["macros"],
        },
    )

    assert imported.status_code == 201, imported.text
    assert imported.json()["corrected"] is False

    app.state.client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    catalogue = (await client.get("/foods")).json()
    assert [food["name"] for food in catalogue] == ["Puerro"]
    assert catalogue[0]["macros"]["kcal"] == 61


async def test_importing_the_same_food_twice_gives_back_the_one_you_have(searching) -> None:
    client = searching(both_answer)
    body = {
        "source": "usda",
        "source_ref": "11246",
        "name": "Puerro",
        "category_id": "vegetable",
        "macros": {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14.15},
    }

    first = await client.post("/foods", json=body)
    second = await client.post("/foods", json=body)

    assert first.json()["id"] == second.json()["id"]
    assert len((await client.get("/foods")).json()) == 1


async def test_what_no_source_has_is_typed_by_hand(api) -> None:
    response = await api.post(
        "/foods/manual",
        json={
            "name": "Sofrito de casa",
            "category_id": "vegetable",
            "macros": {"kcal": 120, "protein": 1.2, "fat": 10.5, "carbs": 6},
            "grams_per_unit": 80,
        },
    )

    assert response.status_code == 201, response.text
    food = response.json()
    assert food["source"] == "manual"
    assert food["source_ref"] is None
    assert food["corrected"] is True
    assert food["grams_per_unit"] == 80


async def test_correcting_the_macros_leaves_it_marked(searching) -> None:
    client = searching(both_answer)
    food = (
        await client.post(
            "/foods",
            json={
                "source": "usda",
                "source_ref": "11246",
                "name": "Puerro",
                "category_id": "vegetable",
                "macros": {"kcal": 61, "protein": 1.5, "fat": 0.3, "carbs": 14.15},
            },
        )
    ).json()

    corrected = await client.put(
        f"/foods/{food['id']}/nutrition",
        json={"macros": {"kcal": 55, "protein": 1.5, "fat": 0.3, "carbs": 12}, "density_g_ml": 0.6},
    )

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["corrected"] is True
    assert corrected.json()["macros"]["kcal"] == 55
    assert corrected.json()["density_g_ml"] == 0.6


async def test_a_category_that_does_not_exist_is_a_404(api) -> None:
    response = await api.post(
        "/foods/manual",
        json={
            "name": "Algo",
            "category_id": "inventada",
            "macros": {"kcal": 10, "protein": 1, "fat": 1, "carbs": 1},
        },
    )

    assert response.status_code == 404
    assert "inventada" in response.json()["detail"]


async def test_impossible_macros_are_refused_before_touching_the_database(api) -> None:
    too_much = await api.post(
        "/foods/manual",
        json={
            "name": "Imposible",
            "category_id": "fat",
            "macros": {"kcal": 4000, "protein": 1, "fat": 1, "carbs": 1},
        },
    )
    negative = await api.post(
        "/foods/manual",
        json={
            "name": "Imposible",
            "category_id": "fat",
            "macros": {"kcal": 100, "protein": -5, "fat": 1, "carbs": 1},
        },
    )

    assert too_much.status_code == 422
    assert negative.status_code == 422


def test_a_barcode_is_looked_up_as_a_product_and_not_as_text() -> None:
    assert looks_like_barcode("8410128750121")
    assert not looks_like_barcode("yogur natural")
    assert not looks_like_barcode("123")


def test_what_the_source_calls_it_becomes_one_of_our_twelve() -> None:
    assert category_hint("Vegetables and Vegetable Products") == "vegetable"
    assert category_hint("Finfish and Shellfish Products") == "fish"
    assert category_hint("Lácteos, Yogures") == "dairy"
    assert category_hint("Cosa rarísima") == "other"
    assert category_hint(None) == "other"


async def test_a_barcode_reaches_the_product_endpoint(searching) -> None:
    asked: list[str] = []

    def by_barcode(request: httpx.Request) -> httpx.Response:
        if "nal.usda.gov" in request.url.host:
            return httpx.Response(200, json={"foods": []})
        asked.append(str(request.url))
        return httpx.Response(200, json={"product": OFF_YOGURT_PRODUCT})

    body = (await searching(by_barcode).get("/foods/search", params={"q": "8410128750121"})).json()

    assert "api/v2/product/8410128750121.json" in asked[0]
    assert [(c["source_ref"], c["brand"]) for c in body["candidates"]] == [
        ("8410128750121", "Marca Sintética")
    ]


async def test_the_server_usda_key_becomes_the_only_persons_credential(
    api, hub, person, monkeypatch
) -> None:
    from uuid import uuid4

    from recipes import publisher

    monkeypatch.setenv("USDA_API_KEY", "clave-del-servidor")

    async def two(_client):
        return [person, uuid4()]

    async def one(_client):
        return [person]

    monkeypatch.setattr(publisher, "users", two)
    assert await publisher.hand_over_usda(app.state.client) is True
    assert (await hub.client.get("/connections")).json() == []

    monkeypatch.setattr(publisher, "users", one)
    assert await publisher.hand_over_usda(app.state.client) is True
    [usda] = (await hub.client.get("/connections")).json()
    assert usda["provider"] == "usda"
    ficha = (await hub.client.get(f"/connections/{usda['id']}")).json()
    assert ficha["secrets"][0]["hint"] == "…idor"
