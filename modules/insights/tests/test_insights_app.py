from __future__ import annotations

from insights_world import insight

from arga_widgets import validate

WRITE = {"x-arga-scopes": "insights:read insights:write"}


async def publish(api, **overrides) -> str:
    response = await api.post("/tools/publish_insight", json=insight(**overrides), headers=WRITE)
    return response.json()["content"]["published"]["insight_id"]


async def test_without_a_name_it_is_called_insights(api) -> None:
    profile = (await api.get("/profile")).json()

    assert profile == {"name": "Insights", "about": "", "named": False}


async def test_each_person_names_it_and_can_go_back(api) -> None:
    named = (await api.put("/profile", json={"name": " Txuri ", "about": ""})).json()
    unnamed = (await api.put("/profile", json={"name": "", "about": "algo"})).json()

    assert (named["name"], named["named"]) == ("Txuri", True)
    assert (unnamed["name"], unnamed["named"], unnamed["about"]) == ("Insights", False, "algo")


async def test_opening_an_insight_clears_the_dot(api) -> None:
    first = await publish(api)
    await publish(api, topic="vitals.peso", domain="body")
    assert (await api.get("/badge")).json() == {"count": 2}

    await api.post(f"/insights/{first}/read")

    assert (await api.get("/badge")).json() == {"count": 1}


async def test_rating_is_reading_and_can_be_undone(api) -> None:
    one = await publish(api)

    rated = (await api.put(f"/insights/{one}/rating", json={"rating": "useful"})).json()
    cleared = (await api.put(f"/insights/{one}/rating", json={"rating": None})).json()

    assert rated["rating"] == "useful" and rated["read_at"] is not None
    assert cleared["rating"] is None and cleared["rated_at"] is None
    assert (await api.get("/badge")).json() == {"count": 0}


async def test_an_insight_that_does_not_exist_is_404(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert (await api.post(f"/insights/{missing}/read")).status_code == 404


async def test_the_card_says_what_it_said_last(api) -> None:
    assert (await api.get("/widgets/latest")).json()["state"] == "empty"
    await publish(api)

    body = (await api.get("/widgets/latest")).json()

    assert body["state"] == "ready"
    validate("list", body["body"], "ready")
    assert body["body"]["rows"][0]["label"] == "Restaurants, 60 % above your usual"
    assert body["body"]["detail"] == "1 unread"
