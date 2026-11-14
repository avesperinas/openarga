from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

import pytest
import test_planner_subscriptions as subscriptions
from test_planner_days_off import EVERY_DAY, work_days, workweek
from test_planner_subscriptions import Hub

kernel = subscriptions.kernel
migrated = subscriptions.migrated
hub_app = subscriptions.hub_app


def nager(day: str, name: str, regions: list[str] | None = None) -> dict:
    return {
        "date": day,
        "localName": name,
        "name": name,
        "global": regions is None,
        "counties": regions,
        "types": ["Public"],
    }


COUNTRIES = {
    "ES": [
        nager("2026-10-12", "National day"),
        nager("2026-10-14", "Navarre day", ["ES-NC"]),
        nager("2026-10-15", "Madrid day", ["ES-MD"]),
    ],
    "DE": [
        nager("2026-10-06", "Federal day"),
        nager("2026-10-08", "Bavaria day", ["DE-BY"]),
        nager("2026-10-09", "Berlin day", ["DE-BE"]),
    ],
}

CASES = [
    ("ES", "ES-NC", {"2026-10-12", "2026-10-14"}),
    ("DE", "DE-BY", {"2026-10-06", "2026-10-08"}),
    ("DE", None, {"2026-10-06"}),
]


@pytest.mark.parametrize(("country", "region", "off"), CASES)
async def test_holidays_free_the_national_days_and_those_of_your_region(
    api, kernel, country: str, region: str | None, off: set[str]
) -> None:
    from hub.providers import holidays

    connection = str(uuid4())
    items = holidays.items_of(COUNTRIES[country], country, region)
    bodies = {one.uid: {k: v for k, v in asdict(one).items() if k != "uid"} for one in items}
    await Hub(kernel, connection).run(bodies, label=f"Holidays · {region or country}")
    layers = (await api.get("/calendars")).json()
    layer = next(one for one in layers if one["connection_id"] == connection)
    work, _ = await workweek(api)

    await api.patch(f"/calendars/{work['id']}", json={"days_off_from": [layer["id"]]})

    assert set(EVERY_DAY) - set(await work_days(api, work["id"])) == off


@pytest.mark.parametrize(("country", "region"), [("ES", "ES-NC"), ("DE", "DE-BY")])
async def test_the_holidays_menu_proposes_where_the_person_lives(
    api, hub_app, country: str, region: str
) -> None:
    headers = {"x-arga-country": country, "x-arga-region": region}

    menu = (await api.get("/subscriptions/catalogue", headers=headers)).json()

    [source] = [one for one in menu["sources"] if one["provider"] == "holidays"]
    asks = {one["key"]: one.get("default") for one in source["asks"]}
    assert asks == {"country": country, "region": region}


async def test_without_a_country_the_menu_keeps_the_source_s_proposal(api, hub_app) -> None:
    plain = (await api.get("/subscriptions/catalogue")).json()
    told = (await api.get("/subscriptions/catalogue", headers={"x-arga-region": "DE-BY"})).json()

    assert plain["sources"] == told["sources"]
