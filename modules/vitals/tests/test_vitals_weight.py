from __future__ import annotations

from datetime import date, timedelta

from vitals import weight


def test_a_day_is_the_mean_of_its_weighings_and_the_average_skips_missing_days() -> None:
    rows = [
        (date(2026, 9, 1), 80.0),
        (date(2026, 9, 1), 81.0),
        (date(2026, 9, 3), 79.0),
        (date(2026, 9, 12), 78.0),
    ]

    days = weight.daily(rows)

    assert [(one.day.day, one.kg, one.avg7) for one in days] == [
        (1, 80.5, 80.5),
        (3, 79.0, 79.75),
        (12, 78.0, 78.0),
    ]


def test_a_change_compares_averages_and_needs_weighings_back_then() -> None:
    start = date(2026, 1, 1)
    days = weight.daily([(start + timedelta(days=n), 90 - n * 0.1) for n in range(100)])

    assert weight.change(days, 30) == -3.0
    assert weight.change(days, 90) == -9.0
    assert weight.change(days[:7], 30) is None
    assert weight.change([], 30) is None


def test_the_band_says_which_way_is_good() -> None:
    band = weight.Goal(weight_min_kg=72, weight_max_kg=76)

    assert weight.against(band, 78) == "above"
    assert weight.against(band, 70) == "below"
    assert weight.against(band, 74) == "inside"
    assert weight.against(weight.Goal(weight_max_kg=76), 70) == "inside"
    assert weight.against(weight.Goal(), 78) is None


async def test_a_weighing_logged_in_the_app_is_in_the_line(api) -> None:
    await api.post("/weight", json={"kg": 80.4, "day": "2026-09-01"})
    await api.post("/weight", json={"kg": 79.6, "day": "2026-09-02", "at": "08:15"})

    found = (await api.get("/weight")).json()

    assert [(one["day"], one["kg"], one["avg7"]) for one in found["days"]] == [
        ("2026-09-01", 80.4, 80.4),
        ("2026-09-02", 79.6, 80.0),
    ]
    assert found["latest"]["avg7"] == 80.0
    assert [one["source"] for one in found["entries"]] == ["manual", "manual"]
    assert found["entries"][0]["at"] == "08:15:00"


async def test_without_a_day_it_is_today(api) -> None:
    logged = (await api.post("/weight", json={"kg": 80})).json()

    assert logged["entry"]["day"] == weight.today().isoformat()


async def test_the_same_weight_the_same_day_is_not_duplicated(api) -> None:
    first = (await api.post("/weight", json={"kg": 80.4, "day": "2026-09-01"})).json()
    again = (await api.post("/weight", json={"kg": 80.40, "day": "2026-09-01"})).json()

    assert again["already"] is True
    assert again["entry"]["id"] == first["entry"]["id"]
    assert len((await api.get("/weight")).json()["entries"]) == 1


async def test_a_weight_out_of_range_is_refused(api) -> None:
    assert (await api.post("/weight", json={"kg": 8.1})).status_code == 422


async def test_a_mistyped_weighing_is_corrected(api) -> None:
    logged = (await api.post("/weight", json={"kg": 87.4, "day": "2026-09-01"})).json()

    fixed = await api.put(
        f"/weight/{logged['entry']['id']}", json={"kg": 78.4, "day": "2026-09-01"}
    )

    assert fixed.status_code == 200
    assert [one["kg"] for one in (await api.get("/weight")).json()["days"]] == [78.4]


async def test_correcting_onto_another_weighing_of_that_day_is_a_conflict(api) -> None:
    await api.post("/weight", json={"kg": 78.4, "day": "2026-09-01"})
    other = (await api.post("/weight", json={"kg": 79.0, "day": "2026-09-01"})).json()

    clash = await api.put(f"/weight/{other['entry']['id']}", json={"kg": 78.4, "day": "2026-09-01"})

    assert clash.status_code == 409


async def test_correcting_what_does_not_exist_is_a_404(api) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert (await api.put(f"/weight/{missing}", json={"kg": 78})).status_code == 404


async def test_the_goal_band_is_kept_and_compared(api) -> None:
    assert (await api.get("/goals")).json() == {
        "steps_per_day": None,
        "weight_min_kg": None,
        "weight_max_kg": None,
        "weight_direction": None,
    }
    await api.put("/goals", json={"steps_per_day": 8000, "weight_min_kg": 72, "weight_max_kg": 76})
    await api.post("/weight", json={"kg": 78, "day": "2026-09-01"})

    found = (await api.get("/weight")).json()

    assert found["goal"]["weight_max_kg"] == 76
    assert found["against_goal"] == "above"


async def test_the_way_the_weight_should_go_is_kept(api) -> None:
    await api.put("/goals", json={"steps_per_day": 8000, "weight_direction": "down"})

    assert (await api.get("/goals")).json()["weight_direction"] == "down"
    assert (await api.get("/kpis")).json()["weight"]["goal"]["weight_direction"] == "down"

    await api.put("/goals", json={"steps_per_day": 8000})

    assert (await api.get("/goals")).json()["weight_direction"] is None


async def test_a_way_that_is_not_up_or_down_is_refused(api) -> None:
    assert (await api.put("/goals", json={"weight_direction": "sideways"})).status_code == 422


async def test_a_band_upside_down_is_refused(api) -> None:
    response = await api.put("/goals", json={"weight_min_kg": 80, "weight_max_kg": 70})

    assert response.status_code == 409


async def test_another_app_logs_a_weight_through_the_kernel_token_only(api, monkeypatch) -> None:
    monkeypatch.setenv("MODULE_REGISTRATION_TOKEN", "the-token")
    body = {"kg": 81.2, "day": "2026-09-03"}

    refused = await api.post("/capabilities/weight.log", json=body)
    unknown = await api.post(
        "/capabilities/weight.erase", json=body, headers={"x-module-token": "the-token"}
    )
    logged = await api.post(
        "/capabilities/weight.log",
        json=body,
        headers={"x-module-token": "the-token", "x-arga-module": "training"},
    )
    again = await api.post(
        "/capabilities/weight.log", json=body, headers={"x-module-token": "the-token"}
    )

    assert refused.status_code == 401
    assert unknown.status_code == 404
    assert logged.status_code == 200
    assert (logged.json()["day"], logged.json()["kg"], logged.json()["already"]) == (
        "2026-09-03",
        81.2,
        False,
    )
    assert again.json()["already"] is True
    found = (await api.get("/weight")).json()
    assert [(one["day"], one["kg"]) for one in found["days"]] == [("2026-09-03", 81.2)]

    fixed = await api.post(
        "/capabilities/weight.log",
        json={"kg": 80.8, "day": "2026-09-03"},
        headers={"x-module-token": "the-token"},
    )
    assert (fixed.json()["id"], fixed.json()["kg"]) == (logged.json()["id"], 80.8)
    found = (await api.get("/weight")).json()
    assert [(one["day"], one["kg"]) for one in found["days"]] == [("2026-09-03", 80.8)]
    assert len(found["entries"]) == 1
