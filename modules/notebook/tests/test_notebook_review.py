from __future__ import annotations

from datetime import timedelta

from arga_widgets import validate
from notebook.notes import today
from notebook.widgets import KINDS


async def note(api, title: str, due: str | None) -> None:
    content = f"---\nnaechste_wiederholung: {due}\nthema: x\n---\n" if due else "no date"
    response = await api.post("/notes", json={"title": title, "content": content})
    assert response.status_code == 201, response.text


async def test_without_a_chosen_property_the_widget_asks_for_one(api) -> None:
    widget = (await api.get("/widgets/review")).json()

    validate(KINDS["review"], widget["body"], widget["state"])
    assert widget["state"] == "empty"
    assert "choose" in widget["body"]["detail"]
    assert (await api.get("/review")).json() == {"chosen": False, "notes": []}


async def test_the_date_properties_are_offered_and_what_is_due_is_listed(api) -> None:
    now = today()
    await note(api, "Late", (now - timedelta(days=3)).isoformat())
    await note(api, "Today", now.isoformat())
    await note(api, "Later", (now + timedelta(days=5)).isoformat())
    await note(api, "Undated", None)

    names = (await api.get("/properties")).json()
    saved = await api.put(
        "/settings", json={"daily_folder": "Diario", "review_property": "naechste_wiederholung"}
    )
    due = (await api.get("/review")).json()
    widget = (await api.get("/widgets/review")).json()

    assert {n["name"]: n["dates"] for n in names} == {"naechste_wiederholung": True, "thema": False}
    assert saved.json()["review_property"] == "naechste_wiederholung"
    assert [n["title"] for n in due["notes"]] == ["Late", "Today"]
    validate(KINDS["review"], widget["body"], widget["state"])
    assert [(r["label"], r["value"]) for r in widget["body"]["rows"]] == [
        ("Late", "3 d ago"),
        ("Today", "today"),
    ]


async def test_the_daily_folder_is_a_setting(api) -> None:
    await api.put("/settings", json={"daily_folder": "Journal", "review_property": None})

    daily = (await api.post("/daily", params={"day": "2026-09-28"})).json()

    assert daily["path"] == "Journal/2026-09-28"
    assert (
        await api.put("/settings", json={"daily_folder": "", "review_property": None})
    ).status_code == 422
