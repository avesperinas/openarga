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
    assert exercise["title"] == "Press banca con barra" and exercise["folder"] == "Ejercicios"
    assert exercise["href"] == f"/training/stats?variante={variant}"
    assert exercise["properties"]["veces"] == 1
    assert exercise["properties"]["mejor_peso_kg"] == 60.0
    assert "Lo más pesado: 8 × 60 kg" in exercise["body"]

    sessions = [one for one in found.values() if one["kind"] == "Sesión"]
    assert len(sessions) == 1
    session = sessions[0]
    day = (T0.date()).fromordinal(T0.date().toordinal() - 1)
    assert session["folder"] == f"Sesiones/{day.year}"
    assert session["properties"]["duracion_min"] == 60
    assert f"[[training:{variant}|Press banca con barra]]: 8 × 60 kg" in session["body"]

    today = found[f"day:{day.isoformat()}"]
    assert today["properties"]["entreno_min"] == 60
    assert today["body"].startswith("- Entreno: [[training:session:")

    untouched = [one for one in found.values() if one["kind"] == "Ejercicio"]
    assert any(one["properties"]["veces"] == 0 for one in untouched)
