from __future__ import annotations

from sqlalchemy import text
from test_training_stats import T0, api, bench, setup, train  # noqa: F401 - fixtures

import arga_contracts as contracts
from training import records
from training.db import engine


async def built() -> dict[str, dict]:
    async with engine().begin() as connection:
        await connection.execute(text('set local role "mod_training"'))
        found = await records.build(connection)
    for one in found:
        assert one == contracts.record(**one)
    return {one["id"]: one for one in found}


async def test_a_session_its_exercises_and_its_day(api) -> None:  # noqa: F811
    await train(api, -1, reps=8, weight="60", push=True)
    variant = await bench(api)

    found = await built()

    exercise = found[variant]
    assert exercise["title"] == "Barbell bench press" and exercise["folder"] == "Exercises"
    assert exercise["href"] == f"/training/stats?variant={variant}"
    assert exercise["properties"]["times"] == 1
    assert exercise["properties"]["best_weight_kg"] == 60.0
    assert "Heaviest: 8 × 60 kg" in exercise["body"]

    sessions = [one for one in found.values() if one["kind"] == "Session"]
    assert len(sessions) == 1
    session = sessions[0]
    day = (T0.date()).fromordinal(T0.date().toordinal() - 1)
    assert session["folder"] == f"Sessions/{day.year}"
    assert session["properties"]["duration_min"] == 60
    assert f"[[training:{variant}|Barbell bench press]]: 8 × 60 kg" in session["body"]

    today = found[f"day:{day.isoformat()}"]
    assert today["properties"]["training_min"] == 60
    assert today["body"].startswith("- Workout: [[training:session:")

    untouched = [one for one in found.values() if one["kind"] == "Exercise"]
    assert any(one["properties"]["times"] == 0 for one in untouched)
