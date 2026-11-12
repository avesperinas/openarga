import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.db import engine
from kernel.main import app
from kernel.ui import SUBJECT_HEADER

YO = "yo@ejemplo.com"
OTRO = "otra.persona@ejemplo.com"


@pytest.fixture
async def api(database_url: str):
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.ui_preferences"))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://kernel",
        headers={SUBJECT_HEADER: YO},
    ) as client:
        yield client
    async with engine().begin() as connection:
        await connection.execute(text("delete from kernel.ui_preferences"))
    await engine().dispose()


async def test_the_first_day_there_are_defaults_and_not_a_404(api) -> None:
    prefs = (await api.get("/ui/preferences")).json()

    assert prefs == {
        "glass_opacity": 0.55,
        "theme": "system",
        "wallpaper": "marea",
        "app_wallpapers": {},
        "app_backgrounds": {},
        "app_names": "standard",
        "custom_app_names": {},
        "icon_style": "solid",
        "home_panels": {"order": [], "hidden": [], "placed": []},
    }


async def test_home_panels_keep_their_order_and_refuse_what_is_not_an_area(api) -> None:
    saved = await api.put(
        "/ui/preferences", json={"home_panels": {"order": ["money", "day"], "hidden": ["mind"]}}
    )
    assert saved.status_code == 200, saved.text
    prefs = (await api.get("/ui/preferences")).json()
    assert prefs["home_panels"] == {"order": ["money", "day"], "hidden": ["mind"], "placed": []}

    wrong = await api.put("/ui/preferences", json={"home_panels": {"order": ["nada"]}})
    assert wrong.status_code == 422


async def test_the_laptop_lowers_it_and_the_phone_respects_it(api) -> None:
    await api.put("/ui/preferences", json={"glass_opacity": 0.35, "theme": "dark"})

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://movil",
        headers={SUBJECT_HEADER: YO},
    ) as phone:
        prefs = (await phone.get("/ui/preferences")).json()

    assert prefs["glass_opacity"] == 0.35
    assert prefs["theme"] == "dark"


async def test_two_people_do_not_share_settings(api) -> None:
    await api.put("/ui/preferences", json={"glass_opacity": 1.0})

    other = (await api.get("/ui/preferences", headers={SUBJECT_HEADER: OTRO})).json()

    assert other["glass_opacity"] == 0.55


async def test_the_last_write_wins_without_a_409(api) -> None:
    await api.put("/ui/preferences", json={"glass_opacity": 0.75})
    await api.put("/ui/preferences", json={"glass_opacity": 0.35})

    assert (await api.get("/ui/preferences")).json()["glass_opacity"] == 0.35


@pytest.mark.parametrize(
    "bad",
    [
        {"glass_opacity": 0.1},
        {"glass_opacity": 1.5},
        {"theme": "neon"},
    ],
)
async def test_a_setting_outside_its_range_is_refused(api, bad: dict) -> None:
    assert (await api.put("/ui/preferences", json=bad)).status_code == 422


async def test_without_the_gateway_header_there_is_nobody(api) -> None:
    assert (await api.get("/ui/preferences", headers={SUBJECT_HEADER: ""})).status_code == 401


async def test_the_wallpaper_travels_like_the_rest(api) -> None:
    await api.put(
        "/ui/preferences",
        json={"glass_opacity": 0.55, "theme": "system", "wallpaper": "pizarra"},
    )

    assert (await api.get("/ui/preferences")).json()["wallpaper"] == "pizarra"


async def test_a_wallpaper_id_that_is_not_an_id_is_refused(api) -> None:
    response = await api.put(
        "/ui/preferences",
        json={"wallpaper": "../../etc/passwd"},
    )

    assert response.status_code == 422


async def test_each_app_can_have_its_own_wallpaper_and_the_rest_keep_the_desktop_one(api) -> None:
    await api.put(
        "/ui/preferences",
        json={"wallpaper": "marea", "app_wallpapers": {"training": "duna"}},
    )

    stored = (await api.get("/ui/preferences")).json()
    assert stored["wallpaper"] == "marea"
    assert stored["app_wallpapers"] == {"training": "duna"}


async def test_an_app_wallpaper_needs_an_app_id_and_a_wallpaper_id(api) -> None:
    for bad in ({"../x": "duna"}, {"training": "../../etc/passwd"}):
        response = await api.put("/ui/preferences", json={"app_wallpapers": bad})
        assert response.status_code == 422


async def test_each_app_keeps_the_background_chosen_for_it(api) -> None:
    await api.put(
        "/ui/preferences",
        json={"app_backgrounds": {"training": "plain", "money": "hue-2"}},
    )

    stored = (await api.get("/ui/preferences")).json()
    assert stored["app_backgrounds"] == {"training": "plain", "money": "hue-2"}


async def test_an_app_background_is_one_of_the_offered(api) -> None:
    for bad in ({"training": "hue-9"}, {"training": "url(x)"}, {"../x": "plain"}):
        response = await api.put("/ui/preferences", json={"app_backgrounds": bad})
        assert response.status_code == 422


async def test_preferences_written_before_app_wallpapers_still_read(api) -> None:
    async with engine().begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.ui_preferences (subject, prefs, updated_at) "
                "values (:s, cast(:p as jsonb), now())"
            ),
            {"s": YO, "p": '{"glass_opacity": 0.7, "theme": "dark", "wallpaper": "pizarra"}'},
        )

    stored = (await api.get("/ui/preferences")).json()
    assert stored["wallpaper"] == "pizarra" and stored["app_wallpapers"] == {}
    assert stored["app_backgrounds"] == {}


async def test_the_names_of_the_apps_travel_with_the_rest(api) -> None:
    await api.put(
        "/ui/preferences",
        json={"theme": "dark", "app_names": "custom", "custom_app_names": {"planner": "Agenda"}},
    )

    stored = (await api.get("/ui/preferences")).json()
    assert stored["app_names"] == "custom"
    assert stored["custom_app_names"] == {"planner": "Agenda"}
    assert stored["theme"] == "dark"


async def test_a_name_set_that_does_not_exist_or_a_bad_custom_name_is_rejected(api) -> None:
    for bad in (
        {"app_names": "klingon"},
        {"custom_app_names": {"../x": "Agenda"}},
        {"custom_app_names": {"planner": ""}},
        {"custom_app_names": {"planner": "x" * 25}},
        {"custom_app_names": {"planner": "dos\nlíneas"}},
    ):
        response = await api.put("/ui/preferences", json=bad)
        assert response.status_code == 422, bad


async def test_the_icon_style_is_kept_and_only_the_three_exist(api) -> None:
    await api.put("/ui/preferences", json={"icon_style": "paper"})
    assert (await api.get("/ui/preferences")).json()["icon_style"] == "paper"

    response = await api.put("/ui/preferences", json={"icon_style": "neon"})
    assert response.status_code == 422
