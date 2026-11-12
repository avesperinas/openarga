import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.db import engine
from kernel.main import app
from kernel.ui import SUBJECT_HEADER

YO = "yo@ejemplo.com"
TABLES = ("ui_device_desktops",)


@pytest.fixture
async def api(database_url: str):
    async with engine().begin() as connection:
        for table in TABLES:
            await connection.execute(text(f"delete from kernel.{table}"))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kernel",
        headers={SUBJECT_HEADER: YO},
    ) as client:
        yield client
    async with engine().begin() as connection:
        for table in TABLES:
            await connection.execute(text(f"delete from kernel.{table}"))
    await engine().dispose()


def item(widget: str, size: str = "2x2") -> dict:
    return {"instance_id": f"i-{widget}", "source": "kernel", "widget": widget, "size": size}


def widgets(desktop: dict) -> list[list[str]]:
    return [[i["widget"] for i in page["items"]] for page in desktop["pages"]]


async def test_the_first_time_both_start_from_the_same_desktop(api) -> None:
    desktops = (await api.get("/ui/desktops")).json()

    assert desktops["mobile"]["default"] is True
    assert desktops["desktop"]["default"] is True
    assert widgets(desktops["mobile"]) == widgets(desktops["desktop"])
    assert [page["id"] for page in desktops["desktop"]["pages"]] == ["hoy", "actividad", "sistema"]


async def test_a_kernel_widget_that_is_gone_is_not_shown(api) -> None:
    await api.put(
        "/ui/desktops/mobile",
        json={"pages": [{"id": "a", "items": [item("sync"), item("events")]}]},
    )

    desktops = (await api.get("/ui/desktops")).json()

    assert widgets(desktops["mobile"]) == [["events"]]


async def test_what_you_add_on_the_phone_does_not_appear_on_the_computer(api) -> None:
    written = await api.put(
        "/ui/desktops/mobile",
        json={"pages": [{"id": "movil", "items": [item("events"), item("version")]}]},
    )
    assert written.status_code == 200, written.text

    desktops = (await api.get("/ui/desktops")).json()

    assert desktops["mobile"]["default"] is False
    assert widgets(desktops["mobile"]) == [["events", "version"]]
    assert desktops["desktop"]["default"] is True
    assert [page["id"] for page in desktops["desktop"]["pages"]] == ["hoy", "actividad", "sistema"]


async def test_each_one_keeps_its_own_screens(api) -> None:
    await api.put("/ui/desktops/mobile", json={"pages": [{"id": "a", "items": [item("events")]}]})
    await api.put(
        "/ui/desktops/desktop",
        json={
            "pages": [
                {"id": "b", "items": [item("version", "4x2")]},
                {"id": "c", "items": [item("entities")]},
            ]
        },
    )

    desktops = (await api.get("/ui/desktops")).json()

    assert widgets(desktops["mobile"]) == [["events"]]
    assert widgets(desktops["desktop"]) == [["version"], ["entities"]]


async def test_editing_on_the_phone_does_not_collide_with_the_computer(api) -> None:
    phone = await api.put("/ui/desktops/mobile", json={"pages": [{"id": "a", "items": []}]})
    computer = await api.put("/ui/desktops/desktop", json={"pages": [{"id": "b", "items": []}]})

    await api.put(
        "/ui/desktops/mobile",
        json={
            "pages": [{"id": "a", "items": [item("events")]}],
            "updated_at": phone.json()["updated_at"],
        },
    )
    again = await api.put(
        "/ui/desktops/desktop",
        json={
            "pages": [{"id": "b", "items": [item("version")]}],
            "updated_at": computer.json()["updated_at"],
        },
    )

    assert again.status_code == 200, again.text


async def test_two_computers_do_not_lose_an_edit_in_silence(api) -> None:
    first = await api.put("/ui/desktops/desktop", json={"pages": [{"id": "a", "items": []}]})
    stale = first.json()["updated_at"]

    await api.put(
        "/ui/desktops/desktop",
        json={"pages": [{"id": "a", "items": [item("entities")]}], "updated_at": stale},
    )
    late = await api.put(
        "/ui/desktops/desktop",
        json={"pages": [{"id": "a", "items": [item("version")]}], "updated_at": stale},
    )

    assert late.status_code == 409
    assert "read it again" in late.json()["detail"]
    stored = (await api.get("/ui/desktops")).json()["desktop"]
    assert widgets(stored) == [["entities"]]


async def test_positions_of_what_is_gone_are_dropped(api) -> None:
    written = await api.put(
        "/ui/desktops/mobile",
        json={
            "pages": [{"id": "a", "items": [item("events")]}],
            "placements": {"tablet": {"a": {"i-events": [0, 0], "i-quitado": [2, 0]}}},
        },
    )

    assert written.json()["placements"] == {"tablet": {"a": {"i-events": [0, 0]}}}


@pytest.mark.parametrize(
    ("device", "body"),
    [
        ("tablet", {"pages": [{"id": "a", "items": []}]}),
        ("mobile", {"pages": [{"id": "a", "items": [item("events")]}, {"id": "a", "items": []}]}),
        ("desktop", {"pages": [{"id": "a", "items": [item("events", "3x1")]}]}),
    ],
    ids=["unknown-device", "same-screen-twice", "unknown-size"],
)
async def test_a_malformed_desktop_is_refused(api, device: str, body: dict) -> None:
    assert (await api.put(f"/ui/desktops/{device}", json=body)).status_code == 422


async def test_the_old_desktops_are_gone(api) -> None:
    written = await api.put(
        "/ui/desktops/mobile", json={"pages": [{"id": "a", "items": [item("events")]}]}
    )
    assert written.status_code == 200, written.text

    async with engine().connect() as connection:
        for table in ("ui_desktops", "ui_layouts", "sync_state"):
            assert await connection.scalar(text(f"select to_regclass('kernel.{table}')")) is None
