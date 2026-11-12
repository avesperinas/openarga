from __future__ import annotations

from datetime import timedelta

import pytest
from test_macros_goals import READ, call, publishers  # noqa: F401 - la fixture se usa por nombre

import arga_contracts as contracts
from macros.common import today


async def weigh(publish, kg: float, day) -> None:
    await publish(
        "vitals",
        "vitals.weight",
        {"body_weight": contracts.body_weight(id=f"w{day}", day=day, kg=kg)},
        f"weight:{day}",
    )


async def test_protein_per_kilo_follows_the_weight(api, world, publishers) -> None:  # noqa: F811
    saved = await call(
        api,
        "set_goal",
        {
            "nutrient": "protein",
            "min": 1.8,
            "unit": "per_kg",
            "valid_from": (today() - timedelta(days=3)).isoformat(),
        },
    )
    assert saved.status_code == 200, saved.text

    day = (await call(api, "get_day", {}, READ)).json()["content"]
    assert "protein" not in {one["nutrient"] for one in day["goals"] if one["source"] == "own"}

    await weigh(publishers, 80, today() - timedelta(days=2))
    found = (await call(api, "get_goals", {}, READ)).json()["content"]
    protein = next(one for one in found["goals"] if one["nutrient"] == "protein")
    assert (protein["unit"], protein["min"], protein["kg"]) == ("per_kg", 1.8, 80)
    assert protein["amount"]["min"] == pytest.approx(144)

    await weigh(publishers, 75, today())
    day = (await call(api, "get_day", {}, READ)).json()["content"]
    goal = next(one for one in day["goals"] if one["nutrient"] == "protein")
    assert goal["goal"]["min"] == pytest.approx(135)
    assert goal["per_kg"] == {"min": 1.8, "max": None, "kg": 75}
    before = (
        await call(api, "get_day", {"day": (today() - timedelta(days=2)).isoformat()}, READ)
    ).json()["content"]
    goal = next(one for one in before["goals"] if one["nutrient"] == "protein")
    assert goal["goal"]["min"] == pytest.approx(144)


async def test_only_energy_and_macros_go_per_kilo(api, world) -> None:
    refused = await call(api, "set_goal", {"nutrient": "fiber", "min": 0.4, "unit": "per_kg"})
    assert refused.status_code == 422
    typo = await call(api, "set_goal", {"nutrient": "protein", "min": 140, "unit": "per_kg"})
    assert typo.status_code == 422
