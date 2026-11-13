from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from test_library_library import add

from library.stats import spread, spread_years


async def read(api, title: str, started: str, finished: str, pages: int, **extra) -> dict:
    response = await api.post(
        "/books",
        json={
            "edition": {
                "title": title,
                "authors": extra.pop("authors", ["Autora"]),
                "pages": pages,
            },
            "reading": {"status": "read", "started_on": started, "finished_on": finished, **extra},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_year_counts_what_was_finished_in_it(api) -> None:
    await read(api, "Largo", "2025-01-01", "2025-01-30", 600, genre="history", rating=4)
    await read(api, "Quick", "2025-03-01", "2025-03-02", 100, genre="novel", rating=5)
    await read(api, "From the other year", "2024-12-20", "2024-12-30", 300, genre="novel")
    await add(api, "En curso", status="reading")
    goal = await api.put("/goals/2025", json={"books": 12})
    assert goal.status_code == 200, goal.text

    found = (await api.get("/stats", params={"year": 2025})).json()

    assert (found["books"], found["pages"], found["goal"]) == (2, 700, 12)
    assert found["average_rating"] == 4.5
    assert found["months"][0]["pages"] == 600 and found["months"][2]["books"] == 1
    assert [g["id"] for g in found["genres"]] == ["history", "novel"]
    assert found["longest"]["title"] == "Largo"
    assert (found["fastest"]["title"], found["fastest"]["days"]) == ("Quick", 2)
    assert found["ratings"] == {"4": 1, "5": 1}
    assert found["days"]["2025-01-01"] == 20.0
    assert found["pages_per_day"] == round(700 / 365, 1)
    assert 2025 in found["years"] and 2024 in found["years"]


async def test_a_goal_can_be_changed_but_not_set_to_nothing(api) -> None:
    await api.put("/goals/2026", json={"books": 10})
    changed = (await api.put("/goals/2026", json={"books": 20})).json()
    zero = await api.put("/goals/2026", json={"books": 0})

    assert changed["goal"] == 20
    assert zero.status_code == 422


def test_a_book_spreads_its_pages_between_its_dates_and_only_inside_the_year() -> None:
    book = SimpleNamespace(pages=40, started_on=date(2025, 12, 31), finished_on=date(2026, 1, 3))

    days = spread([book], 2026)

    assert days == {"2026-01-01": 10.0, "2026-01-02": 10.0, "2026-01-03": 10.0}


def test_several_years_in_one_pass_are_the_years_one_by_one() -> None:
    rows = [
        SimpleNamespace(started_on=date(2023, 12, 20), finished_on=date(2025, 1, 10), pages=388),
        SimpleNamespace(started_on=date(2025, 3, 1), finished_on=date(2025, 3, 3), pages=99),
        SimpleNamespace(started_on=date(2024, 5, 5), finished_on=None, pages=200),
    ]
    one_by_one = {**spread(rows, 2023), **spread(rows, 2025)}

    assert spread_years(rows, {2023, 2025}) == one_by_one
    assert not any(day.startswith("2024") for day in spread_years(rows, {2023, 2025}))
