from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from test_training_stats import T0, api, bench, setup, train  # noqa: F401 - fixtures

import arga_contracts as contracts
from training import metrics, strength
from training.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        found = await metrics.build(connection)
    for one in found:
        assert one == contracts.metric("training", **one)
    return {contracts.metric_identity(one): one for one in found}


async def test_a_session_counts_its_day_and_its_best_set_is_the_mark(api) -> None:  # noqa: F811
    await train(api, -1, reps=8, weight="60", push=True)
    variant = await bench(api)
    day = (T0.date() - timedelta(days=1)).isoformat()

    found = await built()

    sessions = found[f"training.sessions@{day}"]
    assert sessions["value"] == 1 and sessions["kind"] == "amount" and sessions["unit"] == "count"
    mark = found[f"training.e1rm:{variant}@{day}"]
    assert mark["kind"] == "peak" and mark["unit"] == "kg"
    assert mark["value"] == round(strength.epley(8, 60.0), 1)
    assert mark["label"] == "Marca estimada · Press banca con barra"


async def test_the_heaviest_real_weight_of_each_day_is_a_mark(api) -> None:  # noqa: F811
    await train(api, -3, reps=8, weight="60", push=True)
    await train(api, -2, reps=5, weight="70", push=True)
    await train(api, -1, reps=10, weight="50", push=True)
    variant = await bench(api)

    found = await built()
    marks = sorted(
        (one["day"], one["value"])
        for one in found.values()
        if one["key"] == f"training.max:{variant}"
    )
    assert [value for _, value in marks] == [60.0, 70.0, 50.0]
    assert found[f"training.max:{variant}@{marks[0][0]}"]["kind"] == "peak"
    assert (
        found[f"training.max:{variant}@{marks[-1][0]}"]["label"]
        == "Peso máximo · Press banca con barra"
    )
