from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
import pytest
from google_fake import CLIENT_ID, CLIENT_SECRET, REFRESH, FakeGoogle
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import capabilities, worker
from hub.providers import google_health

SECRETS = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
NOW = datetime(2026, 10, 20, 18, 0, tzinfo=UTC)


@pytest.fixture
def fake(monkeypatch) -> FakeGoogle:
    monkeypatch.setattr(google_health, "current", lambda: NOW)
    return FakeGoogle()


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, fake, monkeypatch):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    monkeypatch.setattr(capabilities, "source_transport", lambda: httpx.MockTransport(fake))
    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    await forget(kernel_db)
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    await forget(kernel_db)
    await kernel_db.engine().dispose()


async def forget(kernel_db) -> None:
    async with kernel_db.engine().begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))


async def connect(api) -> UUID:
    started = await api.post(
        "/connections", json={"provider": "google_health", "label": "Pulsera", "secrets": SECRETS}
    )
    assert started.status_code == 201, started.text
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
    back = await api.get(f"/hub/google/callback?state={state}&code=codigo-sintetico")
    assert back.status_code == 303, back.text
    assert back.headers["location"].endswith("?google=conectado")
    return UUID(started.json()["id"])


async def events(schema, event_type: str) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select source, payload, dedup_hash from kernel.events "
                    "where module = 'hub' and type = :type order by ts"
                ),
                {"type": event_type},
            )
        ).all()


async def tick(kernel, fake, person, at: datetime) -> dict:
    async def people() -> list[UUID]:
        return [person]

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as source:
        return await worker.tick(at, False, people=people, source=source, kernel=kernel)


async def test_connecting_goes_to_google_and_comes_back_active(api, kernel, fake) -> None:
    started = await api.post("/connections", json={"provider": "google_health", "secrets": SECRETS})
    asked = parse_qs(urlparse(started.json()["authorization_url"]).query)

    connection = await connect_after(api, asked["state"][0])

    assert asked["client_id"] == [CLIENT_ID]
    assert asked["redirect_uri"] == ["http://localhost:8000/hub/google/callback"]
    assert (asked["access_type"], asked["prompt"]) == (["offline"], ["consent"])
    assert sorted(asked["scope"][0].split()) == sorted(google_health.SCOPES)
    assert all(scope.endswith(".readonly") for scope in google_health.SCOPES)
    ficha = (await api.get(f"/connections/{connection}")).json()
    assert (ficha["state"], ficha["authorizes"]) == ("active", True)
    assert REFRESH not in str(ficha) and CLIENT_SECRET not in str(ficha)


async def connect_after(api, state: str) -> UUID:
    back = await api.get(f"/hub/google/callback?state={state}&code=codigo-sintetico")
    assert back.status_code == 303, back.text
    return UUID(back.headers["location"].split("/hub/")[1].split("?")[0])


async def test_one_per_person_and_reconnecting_is_the_same(api, kernel, fake) -> None:
    connection = await connect(api)

    again = await api.post("/connections", json={"provider": "google_health", "secrets": SECRETS})
    url = (await api.post(f"/connections/{connection}/reauthorize")).json()["authorization_url"]
    state = parse_qs(urlparse(url).query)["state"][0]

    assert again.status_code == 409
    assert "Reconectar" in again.json()["detail"]
    assert await connect_after(api, state) == connection


async def test_a_return_nobody_asked_for_or_cancelled_says_so(api, kernel) -> None:
    unknown = await api.get("/hub/google/callback?state=inventado&code=x")
    cancelled = await api.get("/hub/google/callback?error=access_denied")

    assert unknown.headers["location"] == "/hub/?google=desconocido"
    assert cancelled.headers["location"] == "/hub/?google=cancelado"


async def test_what_is_pasted_is_checked(api, kernel) -> None:
    wrong = await api.post(
        "/connections",
        json={"provider": "google_health", "secrets": {**SECRETS, "client_id": "abc"}},
    )

    assert wrong.status_code == 422 or wrong.status_code == 400
    assert "apps.googleusercontent.com" in wrong.json()["detail"]


async def test_a_pass_brings_every_kind_in_its_contract(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    await connect(api)

    first = await tick(kernel, fake, person, NOW)

    assert first == {str(person): {"Pulsera": "ok"}}
    [steps] = await events(schema, "health.steps")
    assert (steps.source, steps.payload) == ("google_health", {"date": "2026-10-20", "steps": 9120})
    [daily] = await events(schema, "health.daily")
    assert daily.payload == {
        "date": "2026-10-20",
        "metrics": {
            "heart_rate_min": 52.0,
            "heart_rate_avg": 71.4,
            "heart_rate_max": 148.0,
            "resting_heart_rate": 57.0,
            "sleep_heart_rate": 53.2,
            "hrv_ms": 41.3,
            "hrv_deep_ms": 48.7,
            "vo2max": 47.5,
            "active_kcal": 410.5,
            "basal_kcal": 1800.0,
            "distance_km": 6.54,
            "flights": 7.0,
            "active_zone_min": 30.0,
            "light_active_min": 184.0,
            "moderate_active_min": 26.0,
            "vigorous_active_min": 11.0,
            "sedentary_min": 570.0,
            "hr_zone_light_min": 90.0,
            "hr_zone_moderate_min": 20.0,
            "hr_zone_vigorous_min": 8.0,
            "hr_zone_peak_min": 1.0,
            "respiratory_rate": 14.2,
            "respiratory_rate_deep": 13.1,
            "respiratory_rate_light": 14.4,
            "respiratory_rate_rem": 15.0,
            "spo2_pct": 96.4,
            "spo2_min_pct": 93.0,
            "spo2_max_pct": 99.0,
            "skin_temp_delta_c": -0.3,
        },
    }
    [heart] = await events(schema, "health.heart")
    assert heart.payload == {
        "date": "2026-10-20",
        "step": 1,
        "buckets": [
            {"minute": 480, "min": 55.0, "avg": 58.0, "max": 63.0, "steps": 0},
            {"minute": 485, "min": 60.0, "avg": 75.0, "max": 92.0, "steps": 42},
        ],
    }
    [sleep] = await events(schema, "health.sleep")
    assert sleep.payload["date"] == "2026-10-20"
    assert sleep.payload["start"] == "2026-10-20T00:30:00+02:00"
    assert sleep.payload["stages"] == {"deep": 80, "rem": 95, "light": 225, "awake": 35}
    assert (sleep.payload["minutes_asleep"], sleep.payload["minutes_to_fall_asleep"]) == (400, 9)
    assert [one["stage"] for one in sleep.payload["segments"]] == ["light", "deep"]
    assert (
        sleep.payload["awakenings"],
        sleep.payload["minutes_after_wake_up"],
        sleep.payload["minutes_out_of_bed"],
    ) == (12, 6, 4)
    [exercise] = await events(schema, "health.exercise")
    assert exercise.payload == {
        "id": "users/me/dataTypes/exercise/dataPoints/paseo-sintetico",
        "kind": "WALKING",
        "name": "Caminar",
        "start": "2026-10-20T18:00:00+02:00",
        "end": "2026-10-20T18:42:00+02:00",
        "minutes": 40.0,
        "kcal": 180.4,
        "distance_km": 3.2,
        "steps": 4100,
        "heart_rate_avg": 104.0,
        "active_zone_min": 12.0,
        "elevation_gain_m": 38.5,
        "avg_speed_kmh": 4.8,
        "hr_zone_min": {"light": 25.0, "moderate": 12.0, "vigorous": 3.0},
        "cadence_spm": 112.4,
        "stride_length_cm": 74.1,
        "has_gps": True,
        "heart": [{"s": 0, "bpm": 92.0}, {"s": 5, "bpm": 95.4}, {"s": 15, "bpm": 101.0}],
    }
    [ecg] = await events(schema, "health.ecg")
    assert ecg.payload == {
        "id": "users/me/dataTypes/electrocardiogram/dataPoints/ecg-sintetico",
        "start": "2026-10-20T11:00:00+02:00",
        "end": "2026-10-20T11:00:30+02:00",
        "result": "normal_sinus_rhythm",
        "heart_rate_avg": 64.0,
        "sampling_hz": 250,
        "millivolts_scale": 1000,
        "leads": 1,
        "device": "Pulsera sintética",
        "samples": [0, 12, 80, -20, 3],
    }
    [irn] = await events(schema, "health.irn")
    assert irn.payload == {
        "id": "users/me/dataTypes/irregular-rhythm-notification/dataPoints/irn-sintetico",
        "start": "2026-10-20T03:00:00+02:00",
        "end": "2026-10-20T05:00:00+02:00",
        "windows": 3,
        "positive_windows": 2,
    }
    [device] = await events(schema, "health.device")
    assert device.payload == {
        "id": "users/me/pairedDevices/pulsera-sintetica",
        "name": "Pulsera sintética",
        "kind": "tracker",
        "features": ["STEPS", "HEART_RATE", "SPO2"],
        "battery_pct": 82,
        "battery": "high",
        "last_sync": "2026-10-20T17:40:00+00:00",
    }
    [profile] = await events(schema, "health.profile")
    assert profile.payload == {
        "height_cm": 175.5,
        "walking_stride_cm": 74.2,
        "running_stride_cm": 115.0,
        "irn_enrolled": True,
    }


async def test_the_day_s_heart_comes_once_an_hour_and_the_rest_every_quarter(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    quarter = NOW.replace(minute=32)
    monkeypatch.setattr(google_health, "current", lambda: quarter)
    await connect(api)

    assert await tick(kernel, fake, person, quarter) == {str(person): {"Pulsera": "ok"}}

    assert await events(schema, "health.heart") == []
    assert len(await events(schema, "health.exercise")) == 1
    assert google_health.hourly(NOW.replace(minute=2))
    assert not google_health.hourly(quarter)


async def test_a_connection_from_before_the_new_permissions_says_to_reconnect(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api)
    fake.without = {"ecg", "irn", "settings"}

    await tick(kernel, fake, person, NOW)

    ficha = (await api.get(f"/connections/{connection}")).json()
    assert (ficha["state"], ficha["runs"][0]["outcome"]) == ("active", "ok")
    assert ficha["runs"][0]["detail"].count("reconecta Google Health") == 4
    assert "insufficient" not in ficha["runs"][0]["detail"]
    assert await events(schema, "health.ecg") == []
    assert await events(schema, "health.device") == []
    [daily] = await events(schema, "health.daily")
    assert daily.payload["metrics"]["resting_heart_rate"] == 57.0


async def test_a_kind_google_refuses_leaves_the_rest_and_says_so(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api)
    fake.refused_kinds = {"daily-vo2-max"}

    await tick(kernel, fake, person, NOW)

    ficha = (await api.get(f"/connections/{connection}")).json()
    [daily] = await events(schema, "health.daily")
    assert ficha["state"] == "active"
    assert ficha["runs"][0]["outcome"] == "ok"
    assert "daily-vo2-max" in ficha["runs"][0]["detail"]
    assert "vo2max" not in daily.payload["metrics"]
    assert daily.payload["metrics"]["resting_heart_rate"] == 57.0


async def test_repeating_a_pass_publishes_nothing_twice(
    api, kernel, schema, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api)
    await tick(kernel, fake, person, NOW)

    again = (await api.post(f"/connections/{connection}/sync")).json()

    assert again["outcome"] == "ok"
    assert again["runs"][0]["emitted"] == 0


async def test_a_withdrawn_authorisation_leaves_it_expired(
    api, kernel, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api)
    fake.refused_grant = True

    await tick(kernel, fake, person, NOW)

    ficha = (await api.get(f"/connections/{connection}")).json()
    assert ficha["state"] == "expired"
    assert "reconecta" in ficha["runs"][0]["detail"].lower()


async def test_an_account_without_a_google_health_profile_says_so(
    api, kernel, fake, person, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(worker, "HEARTBEAT", tmp_path / "alive")
    connection = await connect(api)
    fake.not_linked = True

    await tick(kernel, fake, person, NOW)

    ficha = (await api.get(f"/connections/{connection}")).json()
    assert ficha["runs"][0]["outcome"] == "error"
    assert "perfil en Google Health" in ficha["runs"][0]["detail"]
