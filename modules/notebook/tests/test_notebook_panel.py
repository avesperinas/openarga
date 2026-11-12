from pathlib import Path

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from notebook import panel as home_panel


async def test_panel_sin_datos_no_revienta(api):
    response = await api.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "mind"


async def test_con_todos_sus_widgets_llenos_el_panel_sella(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "mind"
    assert item["tabs"]
