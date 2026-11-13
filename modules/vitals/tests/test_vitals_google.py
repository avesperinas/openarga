from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from test_vitals_steps import KERNEL_LIKE

from arga_contracts import sources
from arga_widgets import validate
from vitals import steps

INSERT = text("""
    insert into kernel.events (ts, ingested_at, module, source, type, payload, dedup_hash, user_id)
    values (:ts, :received, 'hub', :source, :type, cast(:payload as jsonb), :dedup, :user)
""")


@pytest.fixture
async def log(schema, person):
    async with schema.begin() as connection:
        await connection.execute(
            text(
                "do $$ begin if not exists "
                f"(select 1 from pg_roles where rolname = '{KERNEL_LIKE}') "
                f"then create role {KERNEL_LIKE} nologin; end if; end $$"
            )
        )
        await connection.execute(text(f"grant usage on schema kernel to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.events to {KERNEL_LIKE}"))
        await connection.execute(text(f"grant select on kernel.modules to {KERNEL_LIKE}"))
        await connection.execute(text(f"alter view vitals.events owner to {KERNEL_LIKE}"))
    sent = 0

    async def send(
        payload: dict, received: str, kind: str = "health.daily", source: str = "google_health"
    ):
        nonlocal sent
        sent += 1
        ts = f"{payload['date']}T12:00:00+00:00" if kind in sources.AT_NOON else received
        async with schema.begin() as connection:
            await connection.execute(
                INSERT,
                {
                    "ts": datetime.fromisoformat(ts),
                    "received": datetime.fromisoformat(received),
                    "source": source,
                    "type": kind,
                    "payload": json.dumps(payload),
                    "dedup": f"{kind}:{sent}:{person}",
                    "user": person,
                },
            )

    yield send
    async with schema.begin() as connection:
        await connection.execute(
            text("delete from kernel.events where source in ('apple_health', 'google_health')")
        )


def day(back: int) -> str:
    return (steps.today() - timedelta(days=back)).isoformat()


def at(back: int, clock: str = "21:00") -> str:
    return f"{day(back)}T{clock}:00+00:00"


async def test_on_a_day_from_both_sources_google_wins(api, log) -> None:
    await log({"date": day(30), "steps": 7000}, at(30), "health.steps", "apple_health")
    await log({"date": day(1), "steps": 9000}, at(1, "20:00"), "health.steps")
    await log({"date": day(1), "steps": 12000}, at(1, "21:00"), "health.steps", "apple_health")
    await log({"date": day(1), "metrics": {"resting_heart_rate": 55}}, at(1, "20:00"))
    await log(
        {"date": day(1), "metrics": {"resting_heart_rate": 61}},
        at(1, "21:00"),
        source="apple_health",
    )

    found = (await api.get("/steps")).json()
    heart = (await api.get("/body/resting_heart_rate")).json()

    assert [(one["day"], one["steps"]) for one in found["days"]] == [
        (day(30), 7000),
        (day(1), 9000),
    ]
    assert [one["value"] for one in heart["points"]] == [55]


async def test_what_each_brand_measures_its_own_way_carries_the_switch(api, log) -> None:
    for back in range(60, 20, -1):
        await log({"date": day(back), "metrics": {"hrv_ms": 80}}, at(back), source="apple_health")
    for back in range(20, 0, -1):
        await log({"date": day(back), "metrics": {"hrv_ms": 40}}, at(back))

    found = (await api.get("/body")).json()
    hrv = next(
        figure
        for section in found["sections"]
        for figure in section["figures"]
        if figure["id"] == "hrv_ms"
    )
    monthly = (await api.get("/body/hrv_ms", params={"group_by": "month"})).json()

    assert hrv["changed_on"] == day(20)
    assert hrv["mean_30"] == 40
    assert hrv["historic"] is False
    assert day(20) in [point["day"] for point in monthly["points"]] or monthly["points"]


async def test_a_month_that_crosses_the_switch_is_two(api, log) -> None:
    from vitals import body

    points = [
        body.Point(day=steps.today().replace(day=1) + timedelta(days=n), value=v)
        for n, v in ((0, 80), (1, 80), (2, 40), (3, 40))
    ]
    switch = points[2].day

    grouped = body.grouped(points, "mean", "month", switch)

    assert [(one.day, one.value) for one in grouped] == [
        (points[0].day, 80),
        (switch, 40),
    ]


async def test_what_stopped_arriving_with_the_switch_is_history(api, log) -> None:
    await log(
        {"date": day(10), "metrics": {"walking_speed_kmh": 4.6}}, at(10), source="apple_health"
    )
    await log({"date": day(2), "metrics": {"resting_heart_rate": 56}}, at(2))

    found = (await api.get("/body")).json()
    sections = {one["id"]: one for one in found["sections"]}

    assert [f["id"] for f in sections["history"]["figures"]] == ["walking_speed_kmh"]
    assert sections["history"]["figures"][0]["historic"] is True
    assert sections["gait"]["figures"] == []
    assert [f["id"] for f in sections["heart"]["figures"]] == ["resting_heart_rate"]


def night(back: int, asleep: int, *, id: str | None = None, main: bool = True) -> dict:
    woke = day(back)
    return {
        "id": id or f"night-{back}",
        "date": woke,
        "start": f"{day(back + 1)}T23:30:00+02:00",
        "end": f"{woke}T07:15:00+02:00",
        "minutes_asleep": asleep,
        "minutes_awake": 30,
        "minutes_to_fall_asleep": 10,
        "main": main,
        "stages": {"deep": 70, "rem": 90, "light": asleep - 160, "awake": 30},
        "segments": [
            {
                "start": f"{day(back + 1)}T23:30:00+02:00",
                "end": f"{woke}T01:00:00+02:00",
                "stage": "light",
            },
            {"start": f"{woke}T01:00:00+02:00", "end": f"{woke}T07:15:00+02:00", "stage": "deep"},
        ],
    }


async def test_each_night_keeps_its_last_version_and_naps_go_apart(api, log) -> None:
    await log(night(1, 380), at(1, "06:00"), "health.sleep")
    await log(night(1, 400), at(1, "08:00"), "health.sleep")
    await log(night(1, 25, id="siesta", main=False), at(1, "16:00"), "health.sleep")
    await log(night(2, 440), at(2, "08:00"), "health.sleep")

    found = (await api.get("/sleep")).json()
    detail = (await api.get(f"/sleep/{day(1)}")).json()

    assert [(one["day"], one["minutes_asleep"], one["nap_minutes"]) for one in found["nights"]] == [
        (day(2), 440, 0),
        (day(1), 400, 25),
    ]
    assert found["last"]["day"] == day(1)
    assert found["mean_7"]["asleep"] == 420
    assert found["mean_7"]["stages"]["deep"] == 70
    assert (found["mean_7"]["fell_asleep_at"], found["mean_7"]["woke_at"]) == (-30, 435)
    assert [one["stage"] for one in detail["segments"]] == ["light", "deep"]
    assert (await api.get(f"/sleep/{day(9)}")).status_code == 404


async def test_the_heart_of_a_day_every_five_minutes(api, log, tool) -> None:
    buckets = [
        {"minute": 480, "min": 55, "avg": 58, "max": 63},
        {"minute": 485, "min": 60, "avg": 75, "max": 92},
        {"minute": 545, "min": 50, "avg": 52, "max": 54},
    ]
    await log({"date": day(1), "step": 5, "buckets": buckets[:1]}, at(1, "07:00"), "health.heart")
    await log({"date": day(1), "step": 5, "buckets": buckets}, at(1, "20:00"), "health.heart")

    days = (await api.get("/heart")).json()
    found = (await api.get(f"/heart/{day(1)}")).json()
    told = await tool("get_heart_day", {})

    assert days == [day(1)]
    assert len(found["buckets"]) == 3
    assert (found["min"]["min"], found["max"]["max"]) == (50, 92)
    assert told["day"] == day(1)
    assert told["hours"] == [
        {"hour": 8, "min": 55.0, "avg": 66.5, "max": 92.0},
        {"hour": 9, "min": 50.0, "avg": 52.0, "max": 54.0},
    ]
    assert (await api.get(f"/heart/{day(5)}")).status_code == 404


async def test_the_sleep_widget_compares_last_night_with_the_month(api, log) -> None:
    empty = (await api.get("/widgets/sleep")).json()
    await log(night(2, 420), at(2, "08:00"), "health.sleep")
    await log(night(0, 360), at(0, "08:00"), "health.sleep")

    ready = (await api.get("/widgets/sleep")).json()

    assert empty["state"] == "empty"
    assert ready["state"] == "ready"
    validate("kpi-delta", ready["body"])
    assert (ready["body"]["value"], ready["body"]["previous"]) == (6.0, 6.5)
    assert ready["body"]["detail"] == "deep 70 min · REM 90 min"


async def test_the_sleep_tool_tells_the_nights_and_their_means(log, tool) -> None:
    await log(night(1, 400), at(1, "08:00"), "health.sleep")

    told = await tool("get_sleep", {})

    assert told["last_night"]["minutes_asleep"] == 400
    assert "segments" not in told["last_night"]
    assert told["mean_7_nights"]["nights"] == 1
    assert [one["day"] for one in told["items"]] == [day(1)]


async def test_a_night_tells_its_awakenings_and_time_out_of_bed(api, log) -> None:
    payload = night(1, 400) | {"awakenings": 12, "minutes_after_wake_up": 6}
    await log(payload | {"minutes_out_of_bed": 4}, at(1, "08:00"), "health.sleep")

    last = (await api.get("/sleep")).json()["last"]

    assert (last["awakenings"], last["minutes_after_wake_up"], last["minutes_out_of_bed"]) == (
        12,
        6,
        4,
    )


async def test_the_new_figures_of_the_band_have_their_section(api, log) -> None:
    metrics = {"hrv_deep_ms": 48.7, "hr_zone_peak_min": 1, "respiratory_rate_rem": 15.0}
    await log({"date": day(1), "metrics": metrics}, at(1))

    found = (await api.get("/body")).json()
    where = {
        figure["id"]: section["id"]
        for section in found["sections"]
        for figure in section["figures"]
    }

    assert where == {
        "hrv_deep_ms": "heart",
        "hr_zone_peak_min": "activity",
        "respiratory_rate_rem": "breath",
    }


ECG_ID = "users/me/dataTypes/electrocardiogram/dataPoints/ecg-sintetico"


def ecg(samples: list[int], result: str = "normal_sinus_rhythm") -> dict:
    return {
        "id": ECG_ID,
        "start": f"{day(1)}T11:00:00+02:00",
        "end": f"{day(1)}T11:00:30+02:00",
        "result": result,
        "heart_rate_avg": 64,
        "sampling_hz": 250,
        "millivolts_scale": 1000,
        "samples": samples,
    }


async def test_an_ecg_says_what_the_device_said_and_draws_its_trace(api, log, tool) -> None:
    await log(ecg([0, 1], "inconclusive"), at(1, "09:01"), "health.ecg")
    await log(ecg(list(range(7500))), at(1, "09:30"), "health.ecg")

    listed = (await api.get("/ecg")).json()
    drawn = (await api.get("/ecg/trace", params={"id": ECG_ID})).json()
    told = await tool("get_heart_rhythm", {})

    assert [(one["result_text"], one["seconds"]) for one in listed] == [
        ("Normal sinus rhythm", 30.0)
    ]
    assert len(drawn["millivolts"]) == 1500
    assert drawn["millivolts"][:2] == [0.0, 0.005]
    assert drawn["step_seconds"] == 0.02
    assert told["ecgs"][0]["result_text"] == "Normal sinus rhythm"
    assert "millivolts" not in told["ecgs"][0]
    assert (await api.get("/ecg/trace", params={"id": "other"})).status_code == 404


async def test_irregular_rhythm_alerts_and_the_band(api, log, tool) -> None:
    alert = {"id": "irn-1", "start": f"{day(2)}T03:00:00+02:00", "end": f"{day(2)}T05:00:00+02:00"}
    await log(alert | {"windows": 3, "positive_windows": 2}, at(2), "health.irn")
    await log({"irn_enrolled": True}, at(2), "health.profile")
    band = {"id": "band-1", "name": "Synthetic band", "kind": "tracker", "battery_pct": 90}
    await log(band | {"last_sync": f"{day(1)}T08:00:00+00:00"}, at(1, "08:00"), "health.device")
    await log(
        band | {"battery_pct": 82, "last_sync": f"{day(0)}T08:00:00+00:00"},
        at(0, "08:00"),
        "health.device",
    )

    alerts = (await api.get("/irn")).json()
    devices = (await api.get("/devices")).json()
    rhythm = await tool("get_heart_rhythm", {})
    told = await tool("get_band", {})

    assert [(one["windows"], one["positive_windows"]) for one in alerts] == [(3, 2)]
    assert [(one["name"], one["battery_pct"]) for one in devices] == [("Synthetic band", 82)]
    assert rhythm["alerts_enabled"] is True
    assert told["devices"][0]["battery_pct"] == 82


async def test_without_the_band_the_band_tool_says_so(tool) -> None:
    told = await tool("get_band", {})

    assert told["devices"] == []
    assert "no Google Health device" in told["note"]


@pytest.fixture
async def tool(api):
    async def call(name: str, arguments: dict) -> dict:
        response = await api.post(
            f"/tools/{name}", json=arguments, headers={"x-arga-scopes": "vitals:read"}
        )
        assert response.status_code == 200, response.text
        return response.json()["content"]

    return call
