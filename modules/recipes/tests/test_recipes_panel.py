from pathlib import Path

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from recipes import panel as home_panel


async def test_the_panel_without_data_does_not_break(api):
    response = await api.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "home"


async def test_with_all_its_widgets_full_the_panel_is_sealed(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "home"
    assert item["tabs"]
