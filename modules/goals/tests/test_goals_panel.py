from pathlib import Path

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from goals import panel as home_panel


async def test_panel_sin_datos_no_revienta(api):
    response = await api.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "day"


async def test_lo_apuntado_desde_el_panel_sale_para_hoy_y_manda_en_la_frase(api):
    added = await api.post("/widgets/today/act", json={"verb": "add", "id": "  Llamar al banco "})
    assert added.status_code == 200, added.text
    empty = await api.post("/widgets/today/act", json={"verb": "add", "id": "   "})
    assert empty.status_code == 422

    (item,) = served((await api.get("/panel")).json())
    tasks = item["tabs"][0]["blocks"][0]
    assert tasks["type"] == "tasks" and tasks["widget"] == "today" and tasks["add"]
    assert [one["title"] for one in tasks["items"]] == ["Llamar al banco"]
    assert item["headlines"][0]["text"] == "1 tarea para hoy"

    ticked = await api.post(
        "/widgets/today/act", json={"verb": "complete", "id": tasks["items"][0]["id"]}
    )
    assert ticked.status_code == 200, ticked.text
    (item,) = served((await api.get("/panel")).json())
    assert item["headlines"][0]["text"] == "Nada pendiente para hoy"
    assert item["tabs"][0]["blocks"][0]["items"] == []


async def test_con_todos_sus_widgets_llenos_el_panel_sella(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "day"
    assert item["tabs"]
    assert [tab["id"] for tab in item["tabs"]] == ["tareas"]
