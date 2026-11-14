from pathlib import Path

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from shopping import panel as home_panel


async def test_the_panel_without_data_does_not_break(api):
    response = await api.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "home"


async def test_what_is_added_from_the_panel_goes_to_the_list_and_the_headline(api):
    added = await api.post("/widgets/list/act", json={"verb": "add", "id": "Bread"})
    assert added.status_code == 200, added.text
    (item,) = served((await api.get("/panel")).json())
    block = item["tabs"][0]["blocks"][0]
    assert [one["title"] for one in block["items"]] == ["Bread"]
    assert block["add"]
    assert item["headlines"][0]["text"] == "1 thing left to buy"


async def test_with_every_widget_full_the_panel_is_sealed(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "home"
    assert item["tabs"]
