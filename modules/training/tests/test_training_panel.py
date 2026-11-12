from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from arga_testing.panel import full_panel
from arga_widgets.panel import served
from training import panel as home_panel
from training.main import app


@pytest.fixture
async def client(schema):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://training") as one:
        yield one


async def test_panel_sin_datos_no_revienta(client):
    response = await client.get("/panel")
    assert response.status_code in (200, 404), response.text
    if response.status_code == 200:
        for item in served(response.json()):
            assert item["area"] == "health"


async def test_con_todos_sus_widgets_llenos_el_panel_sella(monkeypatch):
    (item,) = await full_panel(home_panel, Path(__file__).parents[1] / "manifest.yaml", monkeypatch)
    assert item["area"] == "health"
    assert item["tabs"]
