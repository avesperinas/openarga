from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.db import engine
from kernel.desktop import PANEL_APPS, STARTING, default_desktop, tolerated_desktop
from kernel.main import app
from kernel.ui import SUBJECT_HEADER

YO = "yo@ejemplo.com"


@pytest.fixture
async def api(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.ui_device_desktops"))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kernel",
        headers={SUBJECT_HEADER: YO},
    ) as client:
        yield client
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.ui_device_desktops"))
    await engine().dispose()


def item(widget: str, size: str = "2x2") -> dict:
    return {"instance_id": f"i-{widget}", "source": "kernel", "widget": widget, "size": size}


async def test_the_common_one_is_neither_read_nor_written(api) -> None:
    assert (await api.get("/ui/desktop")).status_code in (404, 405)
    written = await api.put("/ui/desktop", json={"pages": [{"id": "a", "items": []}]})
    assert written.status_code in (404, 405)


def test_a_size_from_a_newer_version_does_not_leave_you_without_a_desktop() -> None:
    pages, placements = tolerated_desktop(
        [{"id": "a", "items": [{**item("events"), "size": "9x9"}, {"basura": True}]}],
        {"mobile": {"a": {"i-events": [0, 0]}}, "reloj": {"a": {}}},
    )

    assert [(i.widget, i.size) for i in pages[0].items] == [("events", "2x2")]
    assert placements == {"mobile": {"a": {"i-events": (0, 0)}}}


def test_a_kernel_widget_that_is_gone_is_not_shown() -> None:
    pages, placements = tolerated_desktop(
        [{"id": "a", "items": [item("sync"), item("events")]}],
        {"mobile": {"a": {"i-sync": [0, 0], "i-events": [2, 0]}}},
    )

    assert [i.widget for i in pages[0].items] == ["events"]
    assert placements == {"mobile": {"a": {"i-events": (2, 0)}}}


def test_with_no_app_the_start_is_the_kernel_one() -> None:
    assert [page.id for page in default_desktop(set()).pages] == ["hoy", "actividad", "sistema"]


def test_with_apps_each_device_starts_with_today_health_money_and_the_rest() -> None:
    installed = {
        ("planner", "today"),
        ("planner", "week"),
        ("goals", "today"),
        ("money", "networth"),
        ("vitals", "readiness"),
    }
    mobile = default_desktop(installed, "mobile")
    desktop = default_desktop(installed, "desktop")

    assert [page.id for page in mobile.pages] == ["hoy", "salud", "dinero"]
    assert [page.id for page in desktop.pages] == ["hoy", "salud", "dinero"]
    assert [(i.source, i.widget, i.size, i.option) for i in mobile.pages[0].items] == [
        ("panel", "day", "4x4", None),
        ("planner", "week", "4x2", None),
    ]
    assert [(i.source, i.widget, i.size, i.option) for i in desktop.pages[0].items] == [
        ("panel", "day", "4x6", None),
        ("planner", "week", "4x2", None),
    ]
    for start in (mobile, desktop):
        ids = [item.instance_id for page in start.pages for item in page.items]
        assert len(ids) == len(set(ids))


def test_a_screen_left_empty_does_not_appear() -> None:
    desktop = default_desktop({("money", "networth")}, "desktop")
    assert [page.id for page in desktop.pages] == ["dinero"]
    assert [(i.source, i.widget) for i in desktop.pages[0].items] == [
        ("panel", "money"),
        ("money", "networth"),
    ]


def test_every_starting_widget_is_one_its_app_declares_in_that_size() -> None:
    manifests = {
        path.parent.name: yaml.safe_load(path.read_text())
        for path in (Path(__file__).resolve().parents[2] / "modules").glob("*/manifest.yaml")
    }
    sizes = {
        (app, widget["id"]): set(widget.get("sizes", []))
        for app, manifest in manifests.items()
        for widget in (manifest.get("ui") or {}).get("widgets") or []
    }
    for device, pages in STARTING.items():
        for _, placed in pages:
            for source, widget, size, option in placed:
                if source == "panel":
                    area = widget.removesuffix(".tab")
                    assert area in PANEL_APPS, (device, widget)
                    assert size in (("2x2", "4x2", "4x4") if option else ("4x6", "4x4"))
                    if option:
                        assert option.split(".", 1)[0] in PANEL_APPS[area], (device, option)
                    continue
                assert (source, widget) in sizes, (device, source, widget)
                assert size in sizes[(source, widget)], (device, source, widget, size)


async def test_what_was_chosen_when_placing_a_widget_survives_a_reload(api) -> None:
    one = item("version") | {"instance_id": "saldo-a", "option": "cuenta_a"}
    two = item("version") | {"instance_id": "saldo-b", "option": "cuenta_b"}
    plain = item("events")
    written = await api.put(
        "/ui/desktops/mobile", json={"pages": [{"id": "inicio", "items": [one, two, plain]}]}
    )
    assert written.status_code == 200, written.text
    again = written.json()["pages"][0]["items"]
    assert [(i["instance_id"], i.get("option")) for i in again] == [
        ("saldo-a", "cuenta_a"),
        ("saldo-b", "cuenta_b"),
        ("i-events", None),
    ]
