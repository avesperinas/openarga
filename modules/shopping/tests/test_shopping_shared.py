from __future__ import annotations

from uuid import UUID

import pytest

from arga_tenancy import SPACES_HEADER, USER_HEADER

ANA = UUID("0a0a0a0a-0000-4000-8000-00000000a0a0")
LUIS = UUID("0b0b0b0b-0000-4000-8000-00000000b0b0")
EVA = UUID("0e0e0e0e-0000-4000-8000-00000000e0e0")
CASA = UUID("0c0c0c0c-0000-4000-8000-00000000c0c0")
WRITE_SCOPES = {"x-arga-scopes": "shopping:write"}


def who(person: UUID, *spaces: UUID) -> dict[str, str]:
    headers = {USER_HEADER: str(person)}
    if spaces:
        headers[SPACES_HEADER] = ",".join(str(one) for one in spaces)
    return headers


def names(shopping: dict) -> list[str]:
    return sorted(
        [one["name"] for group in shopping["groups"] for one in group["items"]]
        + [one["name"] for one in shopping["cart"]]
    )


async def add(api, headers: dict, *products: str) -> dict:
    response = await api.post(
        "/list/items", json={"items": [{"name": one} for one in products]}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["list"]


async def use(api, headers: dict, space: UUID | None) -> dict:
    response = await api.put(
        "/list/owner", json={"space_id": str(space) if space else None}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_your_list_is_yours_until_you_choose_a_home(api) -> None:
    await add(api, who(ANA, CASA), "Bread")

    shopping = (await api.get("/list", headers=who(ANA, CASA))).json()

    assert shopping["space_id"] is None
    assert names(shopping) == ["Bread"]


async def test_both_members_see_and_mark_the_same_home_list(api) -> None:
    await use(api, who(ANA, CASA), CASA)
    await use(api, who(LUIS, CASA), CASA)
    added = await add(api, who(ANA, CASA), "Milk", "Eggs")
    milk = next(one for g in added["groups"] for one in g["items"] if one["name"] == "Milk")

    marked = await api.put(
        f"/list/items/{milk['id']}/cart", json={"in_cart": True}, headers=who(LUIS, CASA)
    )
    ana = (await api.get("/list", headers=who(ANA, CASA))).json()

    assert marked.status_code == 200
    assert names(marked.json()) == ["Eggs", "Milk"]
    assert marked.json()["space_id"] == str(CASA)
    assert [one["name"] for one in ana["cart"]] == ["Milk"]


async def test_choosing_a_home_moves_nothing_and_going_back_finds_your_list(api) -> None:
    await add(api, who(ANA, CASA), "Bread")

    home = await use(api, who(ANA, CASA), CASA)
    await add(api, who(ANA, CASA), "Bread")
    back = await use(api, who(ANA, CASA), None)

    assert names(home) == []
    assert names(back) == ["Bread"]
    products = (await api.get("/products", headers=who(ANA, CASA))).json()
    assert [one["name"] for one in products] == ["Bread"]


async def test_the_home_list_is_not_yours_if_you_do_not_choose_it(api) -> None:
    await use(api, who(ANA, CASA), CASA)
    await add(api, who(ANA, CASA), "Milk")

    luis = (await api.get("/list", headers=who(LUIS, CASA))).json()

    assert luis["space_id"] is None
    assert names(luis) == []


async def test_a_space_you_are_not_in_is_not_a_list_you_can_use(api) -> None:
    response = await api.put("/list/owner", json={"space_id": str(CASA)}, headers=who(EVA))

    assert response.status_code == 404


async def test_whoever_left_the_space_is_back_on_their_own_list(api) -> None:
    await add(api, who(LUIS), "Kefir")
    await use(api, who(LUIS, CASA), CASA)
    await add(api, who(LUIS, CASA), "Milk")

    after = (await api.get("/list", headers=who(LUIS))).json()

    assert after["space_id"] is None
    assert names(after) == ["Kefir"]


async def test_a_finished_trip_is_in_the_home_history_and_not_in_yours(api) -> None:
    await use(api, who(ANA, CASA), CASA)
    await use(api, who(LUIS, CASA), CASA)
    added = await add(api, who(ANA, CASA), "Milk")
    item = added["groups"][0]["items"][0]["id"]
    await api.put(f"/list/items/{item}/cart", json={"in_cart": True}, headers=who(ANA, CASA))

    finished = await api.post("/list/finish", headers=who(LUIS, CASA))
    luis = (await api.get("/trips", headers=who(LUIS, CASA))).json()
    await use(api, who(ANA, CASA), None)
    ana_own = (await api.get("/trips", headers=who(ANA, CASA))).json()

    assert finished.status_code == 201
    assert [[p["name"] for p in trip["products"]] for trip in luis] == [["Milk"]]
    assert ana_own == []


async def test_claude_and_the_widgets_use_the_list_you_chose(api) -> None:
    await use(api, who(ANA, CASA), CASA)
    await use(api, who(LUIS, CASA), CASA)

    told = await api.post(
        "/tools/add_to_list",
        json={"items": [{"name": "Coffee"}]},
        headers=who(ANA, CASA) | WRITE_SCOPES,
    )
    card = (await api.get("/widgets/list", headers=who(LUIS, CASA))).json()
    read = await api.post(
        "/tools/get_shopping_list", json={}, headers=who(LUIS, CASA) | WRITE_SCOPES
    )

    assert told.status_code == 200
    assert told.json()["content"]["shared"] is True
    assert [task["title"] for task in card["body"]["tasks"]] == ["Coffee"]
    assert read.json()["content"]["shared"] is True
    assert read.json()["content"]["pending"] == 1


@pytest.mark.parametrize("space", [None, CASA])
async def test_what_you_chose_is_only_yours(api, space: UUID | None) -> None:
    await use(api, who(ANA, CASA), space)

    luis = (await api.get("/list", headers=who(LUIS, CASA))).json()

    assert luis["space_id"] is None
