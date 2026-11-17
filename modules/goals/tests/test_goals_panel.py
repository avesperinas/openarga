from pathlib import Path

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from goals import panel as home_panel


async def test_the_panel_without_data_does_not_break(api):
    response = await api.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "day"


async def test_what_is_added_from_the_panel_is_for_today_and_leads_the_headline(api):
    added = await api.post("/widgets/today/act", json={"verb": "add", "id": "  Call the bank "})
    assert added.status_code == 200, added.text
    empty = await api.post("/widgets/today/act", json={"verb": "add", "id": "   "})
    assert empty.status_code == 422

    (item,) = served((await api.get("/panel")).json())
    tasks = item["tabs"][0]["blocks"][0]
    assert tasks["type"] == "tasks" and tasks["widget"] == "today" and tasks["add"]
    assert [one["title"] for one in tasks["items"]] == ["Call the bank"]
    assert item["headlines"][0]["text"] == "1 task for today"

    ticked = await api.post(
        "/widgets/today/act", json={"verb": "complete", "id": tasks["items"][0]["id"]}
    )
    assert ticked.status_code == 200, ticked.text
    (item,) = served((await api.get("/panel")).json())
    assert item["headlines"][0]["text"] == "Nothing pending for today"
    assert item["tabs"][0]["blocks"][0]["items"] == []


async def test_with_all_its_widgets_full_the_panel_seals(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "day"
    assert item["tabs"]
    assert [tab["id"] for tab in item["tabs"]] == ["tasks"]
