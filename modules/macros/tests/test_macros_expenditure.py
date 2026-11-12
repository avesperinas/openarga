from __future__ import annotations

from datetime import timedelta

import pytest
from test_macros_goals import READ, WRITE, call, publishers  # noqa: F401 - la fixture por nombre

import arga_contracts as contracts
from macros import expenditure
from macros.common import today


def test_the_basal_floor_by_sex_age_and_weight() -> None:
    assert expenditure.bmr("male", 45, 80) == 1729
    assert expenditure.bmr("female", 25, 60) == 1344
    assert expenditure.bmr(None, 45, 80) == round((14.2 * 80 + 593 + 9.74 * 80 + 694) / 2)


def test_the_trend_of_the_weight_is_its_least_squares_slope() -> None:
    assert expenditure.slope([(0, 80.0), (10, 79.0), (20, 78.0)]) == pytest.approx(-0.1)
    assert expenditure.slope([(5, 80.0)]) == 0.0


def test_a_proposal_is_said_in_words() -> None:
    lose = expenditure.Proposal(rate_kg_week=-0.3, kcal=2150)
    assert expenditure.proposal_label(lose) == "Para bajar 0,3 kg por semana, 2.150 kcal"
    keep = expenditure.Proposal(rate_kg_week=0, kcal=2450)
    assert expenditure.proposal_label(keep) == "Para mantener el peso, 2.450 kcal"


async def eat_days(api, world, days: list, kcal: float) -> None:
    for day in days:
        logged = await api.post(
            "/entries",
            json={
                "eaten_at": f"{day.isoformat()}T14:00:00",
                "items": [{"kind": "quick", "name": "Guiso", "quantity": kcal, "unit": "kcal"}],
            },
        )
        assert logged.status_code == 201, logged.text


async def test_it_needs_complete_days_and_the_weight(api, world, publishers) -> None:  # noqa: F811
    days = [today() - timedelta(days=back) for back in range(1, 28)]
    await eat_days(api, world, days, 2000)

    week = (await call(api, "get_week", {}, READ)).json()["content"]["expenditure"]
    assert week["kcal"] is None
    assert "14 días completos" in week["missing"]

    for day in days[:13]:
        marked = await api.put(f"/day-complete/{day.isoformat()}", json={"complete": True})
        assert marked.status_code == 200, marked.text
    told = await call(api, "mark_day_complete", {"day": days[13].isoformat()})
    assert told.json()["content"] == {"day": days[13].isoformat(), "complete": True}
    assert (await api.get("/day", params={"day": days[13].isoformat()})).json()["complete"]

    week = (await call(api, "get_week", {}, READ)).json()["content"]["expenditure"]
    assert week["kcal"] is None
    assert "peso" in week["missing"]

    first, last = days[-1], days[0]
    for day, kg in ((first, 80.0), (last, 79.4)):
        await publishers(
            "vitals",
            "vitals.weight",
            {"body_weight": contracts.body_weight(id=f"w{day}", day=day, kg=kg)},
            f"weight:{day}",
        )

    week = (await call(api, "get_week", {}, READ)).json()["content"]["expenditure"]
    assert week["days"] == 14
    assert week["intake"] == 2000
    assert week["kcal"] == 2200
    keep, lose = week["proposals"]
    assert (keep["kcal"], keep["said"]) == (2200, "Para mantener el peso, 2.200 kcal")
    assert lose["kcal"] == 1850
    assert lose["said"] == "Para bajar 0,3 kg por semana, 1.850 kcal"


async def test_tomorrow_cannot_be_complete(api, world) -> None:
    refused = await api.put(
        f"/day-complete/{(today() + timedelta(days=1)).isoformat()}", json={"complete": True}
    )
    assert refused.status_code == 409


async def test_nothing_is_proposed_below_the_basal_floor(api, world, publishers) -> None:  # noqa: F811
    days = [today() - timedelta(days=back) for back in range(1, 15)]
    await eat_days(api, world, days, 1300)
    for day in days:
        await api.put(f"/day-complete/{day.isoformat()}", json={"complete": True})
    for day, kg in ((days[-1], 90.0), (days[0], 90.0)):
        await publishers(
            "vitals",
            "vitals.weight",
            {"body_weight": contracts.body_weight(id=f"w{day}", day=day, kg=kg)},
            f"weight:{day}",
        )
    week = (await call(api, "get_week", {}, READ)).json()["content"]["expenditure"]
    lose = week["proposals"][1]
    assert lose["floored"] is True
    assert lose["kcal"] >= week["bmr"]
    assert WRITE
