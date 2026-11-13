from pathlib import Path

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from planner import panel as home_panel


async def test_panel_sin_datos_no_revienta(api):
    response = await api.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "day"


async def test_with_every_widget_full_the_panel_seals(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "day"
    tabs = {tab["id"]: tab for tab in item["tabs"]}
    (month,) = tabs["month"]["blocks"]
    assert month["type"] == "month" and month["marked"] == [3, 6, 8]


async def test_tomorrow_does_not_count_as_today(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from planner import widgets

    today = datetime.now(ZoneInfo(widgets.HOME_TZ)).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    entries = [
        {"start": today.isoformat(), "end": tomorrow, "all_day": True, "title": "Presupuesto"},
        {"start": f"{tomorrow}T18:30:00+01:00", "end": f"{tomorrow}T19:30:00+01:00", "title": "A"},
        {"start": f"{tomorrow}T20:30:00+01:00", "end": f"{tomorrow}T22:30:00+01:00", "title": "B"},
    ]

    async def gather(connection, renderers, keys):
        return {"today": {"state": "ready", "body": {"entries": entries}}}

    monkeypatch.setattr(home_panel, "gather", gather)
    (item,) = served(await home_panel.build(None))
    (agenda,) = [tab for tab in item["tabs"] if tab["id"] == "today"]
    alert, tiles, later = agenda["blocks"]
    assert alert["type"] == "alert"
    assert {tile["label"]: tile["value"] for tile in tiles["items"]} == {
        "Today": "Free",
        "This week": "3",
    }
    assert [row["label"] for row in later["rows"]] == ["A", "B"]
    assert [line["text"] for line in item["headlines"]] == ["Nothing on the calendar today"]
