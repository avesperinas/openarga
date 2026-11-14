from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from insights_world import insight
from sqlalchemy import text

from insights import passes, worker

MADRID = ZoneInfo("Europe/Madrid")


METER = "probe_meter"
READ = {"x-arga-scopes": "insights:read"}
WRITE = {"x-arga-scopes": "insights:read insights:write"}
MORNING = datetime(2026, 10, 13, 8, 0, tzinfo=MADRID)
SUNDAY = datetime(2026, 10, 18, 19, 0, tzinfo=MADRID)


@pytest.fixture
async def meter(schema):
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": METER})
        await connection.execute(
            text(
                "insert into kernel.modules (id, version, enabled, manifest) "
                "values (:m, '0.1.0', true, cast(:manifest as jsonb)) "
                "on conflict (id) do update set manifest = excluded.manifest"
            ),
            {
                "m": METER,
                "manifest": json.dumps(
                    {
                        "id": METER,
                        "publishes": [
                            {"type": f"{METER}.metric", "contract": "metric"},
                            {"type": f"{METER}.record", "contract": "record"},
                        ],
                    }
                ),
            },
        )
    yield schema
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = :m"), {"m": METER})
        await connection.execute(text("delete from kernel.modules where id = :m"), {"m": METER})


async def emit(engine, kind: str, payload: dict, dedup: str, ts: datetime) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash, "
                "user_id) values (:ts, :m, 'app', :type, cast(:payload as jsonb), :dedup, "
                "nullif(current_setting('arga.user_id', true), '')::uuid)"
            ),
            {
                "ts": ts,
                "m": METER,
                "type": f"{METER}.{kind}",
                "payload": json.dumps(payload),
                "dedup": dedup,
            },
        )


async def weights(engine, until: datetime, last: float | None = None) -> None:
    noise = random.Random(5)
    end = until.date()
    for back in range(80, -1, -1):
        day = end - timedelta(days=back)
        value = last if back == 0 and last is not None else 80 + noise.uniform(-0.4, 0.4)
        point = {
            "key": f"{METER}.weight",
            "label": "Weight",
            "unit": "kg",
            "kind": "level",
            "day": day.isoformat(),
            "value": round(value, 2),
        }
        ts = datetime.combine(day, datetime.min.time(), MADRID)
        await emit(engine, "metric", {"metric": point}, f"w@{day}:{value}", ts)


async def goal_behind(engine) -> None:
    record = {
        "id": "goal:1",
        "title": "Cholesterol under 200",
        "kind": "Goal",
        "href": "/goals/goal/1",
        "folder": "Goals",
        "properties": {
            "status": "active",
            "pace": "behind",
            "current": 255,
            "target": 200,
            "expected": 221,
            "unit": "mg/dL",
            "due": "2026-12-31",
        },
        "body": "",
    }
    await emit(engine, "record", {"record": record}, "goal:1:v1", datetime.now(UTC))


class FakeHub:
    def __init__(self, answer: dict | None = None) -> None:
        self.asked: list[dict] = []
        self.answer = answer or {"outcome": "queued", "run": "r", "repeated": False}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/capabilities/claude.run"
        assert request.headers["x-arga-module"] == "insights"
        self.asked.append(json.loads(request.content))
        return httpx.Response(200, json=self.answer)


@pytest.fixture
def hub(monkeypatch) -> FakeHub:
    fake = FakeHub()
    monkeypatch.setattr(passes, "transport", lambda: httpx.MockTransport(fake))
    return fake


async def run(kind: str, key: str, now: datetime):
    from insights.main import as_role

    async with as_role("mod_insights") as connection:
        return await passes.run(connection, kind, key, now)


async def test_a_weight_jump_is_a_signal_and_the_series_is_there(meter, api) -> None:
    now = datetime.now(MADRID)
    await weights(meter, now, last=82.0)
    await goal_behind(meter)

    found = (await api.post("/tools/get_signals", json={}, headers=READ)).json()["content"]
    listed = (await api.post("/tools/get_series", json={}, headers=READ)).json()["content"]
    series = (
        await api.post(
            "/tools/get_series", json={"keys": [f"{METER}.weight", "nothing.x"]}, headers=READ
        )
    ).json()["content"]

    kinds = {one["id"]: one for one in found["signals"]}
    assert kinds[f"deviation:{METER}.weight"]["value"] == 82.0
    assert kinds["goal:goal:1"]["baseline"] == 221
    assert [one["key"] for one in listed["metrics"]] == [f"{METER}.weight"]
    assert len(series["series"][0]["points"]) == 81
    assert series["note"] == "no figures with those keys: nothing.x"


async def test_the_app_shows_the_signals_of_the_week(meter, api) -> None:
    await weights(meter, datetime.now(MADRID), last=82.0)

    shown = (await api.get("/signals")).json()

    assert [one["kind"] for one in shown] == ["deviation"]
    assert "Weight" in shown[0]["text"]


def test_what_is_due_depends_on_the_hour_and_the_day() -> None:
    assert passes.due(MORNING.replace(hour=6)) == []
    assert passes.due(MORNING) == [("morning", "morning:2026-10-13")]
    assert passes.due(MORNING.replace(hour=22)) == []
    assert passes.due(SUNDAY) == [("morning", "morning:2026-10-18"), ("weekly", "weekly:2026-W42")]
    monday = SUNDAY + timedelta(days=1)
    assert passes.due(monday.replace(hour=6)) == [("weekly", "weekly:2026-W42")]
    assert passes.due(monday.replace(hour=9)) == [
        ("morning", "morning:2026-10-19"),
        ("weekly", "weekly:2026-W42"),
    ]
    assert passes.due(monday.replace(hour=12)) == [("morning", "morning:2026-10-19")]


async def test_a_morning_with_something_new_asks_your_claude_once(meter, api, hub) -> None:
    await api.put("/profile", json={"name": "Txuri", "about": "I want to get to 78 kg."})
    await weights(meter, MORNING, last=82.0)

    first = await run("morning", "morning:2026-10-13", MORNING)
    again = await run("morning", "morning:2026-10-13", MORNING + timedelta(hours=1))

    assert (first, again) == ("queued", None)
    (asked,) = hub.asked
    assert asked["key"] == "morning:2026-10-13"
    assert asked["wait_for_room"] is True
    assert "tools" not in asked
    prompt = asked["prompt"]
    assert "You are Txuri" in prompt and "I want to get to 78 kg." in prompt
    assert f"[deviation:{METER}.weight] Weight: 82 kg" in prompt
    assert "at most two pieces of advice" in prompt
    assert "Do not use insights_reply" in prompt


async def ended(engine, key: str, outcome: str, code: str | None = None, **extra) -> None:
    payload = {"key": f"insights:{key}", "outcome": outcome, "code": code, "detail": "…", **extra}
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash, "
                "user_id) values (now(), 'hub', 'hub', 'hub.run', "
                "cast(:payload as jsonb), :dedup, "
                "nullif(current_setting('arga.user_id', true), '')::uuid)"
            ),
            {"payload": json.dumps(payload), "dedup": f"run:insights:{key}"},
        )


@pytest.fixture
async def hub_runs(schema):
    yield schema
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))


async def test_the_same_signals_the_next_morning_do_not_wake_your_claude(
    meter, api, hub, hub_runs
) -> None:
    await weights(meter, MORNING, last=82.0)
    await run("morning", "morning:2026-10-13", MORNING)
    await ended(hub_runs, "morning:2026-10-13", "ok")

    tomorrow = MORNING + timedelta(days=1)
    quiet = await run("morning", "morning:2026-10-14", tomorrow)

    assert quiet == "quiet"
    assert len(hub.asked) == 1


async def test_signals_of_a_morning_that_did_not_end_well_are_still_new(
    meter, api, hub, hub_runs
) -> None:
    await weights(meter, MORNING, last=82.0)
    await run("morning", "morning:2026-10-13", MORNING)
    await ended(hub_runs, "morning:2026-10-13", "skipped", "no_room")

    tomorrow = MORNING + timedelta(days=1)
    assert await run("morning", "morning:2026-10-14", tomorrow) == "queued"
    assert [one["key"] for one in hub.asked] == ["morning:2026-10-13", "morning:2026-10-14"]


async def test_a_pass_that_ended_badly_is_asked_again_up_to_three_times(
    meter, api, hub, hub_runs
) -> None:
    await weights(meter, MORNING, last=82.0)
    key = "morning:2026-10-13"

    assert await run("morning", key, MORNING) == "queued"
    assert await run("morning", key, MORNING + timedelta(hours=1)) is None
    await ended(hub_runs, key, "error")
    assert await run("morning", key, MORNING + timedelta(hours=2)) == "queued"
    await ended(hub_runs, f"{key}#2", "rate_limited")
    assert await run("morning", key, MORNING + timedelta(hours=3)) == "queued"
    await ended(hub_runs, f"{key}#3", "error")
    assert await run("morning", key, MORNING + timedelta(hours=4)) is None

    assert [one["key"] for one in hub.asked] == [key, f"{key}#2", f"{key}#3"]
    [last] = (await api.get("/runs")).json()
    assert (last["state"], last["attempt"]) == ("error", 3)
    assert last["fix"] == "It was tried three times: the next one is tomorrow."


async def test_a_pass_that_went_well_is_not_asked_again(meter, api, hub, hub_runs) -> None:
    await weights(meter, MORNING, last=82.0)
    await run("morning", "morning:2026-10-13", MORNING)
    await ended(hub_runs, "morning:2026-10-13", "ok", ran_with="Otra")

    assert await run("morning", "morning:2026-10-13", MORNING + timedelta(hours=1)) is None
    [last] = (await api.get("/runs")).json()
    assert (last["state"], last["ran_with"]) == ("ok", "Otra")


async def test_the_runs_say_why_insights_is_quiet_to_claude(meter, api, hub, hub_runs) -> None:
    await weights(meter, MORNING, last=82.0)
    await run("morning", "morning:2026-10-13", MORNING)
    await ended(hub_runs, "morning:2026-10-13", "skipped", "no_room")

    answer = (await api.post("/tools/get_runs", json={}, headers=READ)).json()["content"]
    [one] = answer["runs"]
    assert (one["key"], one["state"]) == ("morning:2026-10-13", "skipped")
    assert one["fix"] == "Your AI has no room right now: it will be asked again on its own."


async def test_a_morning_with_nothing_stays_quiet(meter, api, hub) -> None:
    await weights(meter, MORNING)

    assert await run("morning", "morning:2026-10-13", MORNING) == "quiet"
    assert hub.asked == []
    [last] = (await api.get("/runs")).json()
    assert (last["kind"], last["state"], last["signals"]) == ("morning", "quiet", 0)


async def test_without_permission_it_says_how_and_tries_again(meter, api, monkeypatch) -> None:
    refused = FakeHub({"outcome": "skipped", "code": "not_granted", "detail": "…"})
    monkeypatch.setattr(passes, "transport", lambda: httpx.MockTransport(refused))
    await weights(meter, MORNING, last=82.0)

    first = await run("morning", "morning:2026-10-13", MORNING)
    again = await run("morning", "morning:2026-10-13", MORNING + timedelta(hours=1))

    assert (first, again) == ("refused", "refused")
    [last] = (await api.get("/runs")).json()
    assert last["state"] == "refused"
    assert "allow it in Hub" in last["detail"]


async def test_the_run_tells_how_it_ended_in_hub(meter, api, hub, schema) -> None:
    await weights(meter, MORNING, last=82.0)
    await run("morning", "morning:2026-10-13", MORNING)
    waiting = (await api.get("/runs")).json()[0]["state"]

    async with schema.begin() as connection:
        await connection.execute(
            text(
                "insert into kernel.events (ts, module, source, type, payload, dedup_hash, "
                "user_id) values (now(), 'hub', 'hub', 'hub.run', "
                "cast(:payload as jsonb), :dedup, "
                "nullif(current_setting('arga.user_id', true), '')::uuid)"
            ),
            {
                "payload": json.dumps(
                    {"key": "insights:morning:2026-10-13", "outcome": "ok", "detail": "Hecho"}
                ),
                "dedup": "run:insights:morning:2026-10-13",
            },
        )
    ended = (await api.get("/runs")).json()[0]

    assert waiting == "waiting"
    assert (ended["state"], ended["detail"]) == ("ok", "Hecho")
    async with schema.begin() as connection:
        await connection.execute(text("delete from kernel.events where module = 'hub'"))


async def test_the_summary_asked_again_on_monday_is_the_week_before(
    meter, api, hub, hub_runs
) -> None:
    await weights(meter, SUNDAY)
    await run("weekly", "weekly:2026-W42", SUNDAY)
    await ended(hub_runs, "weekly:2026-W42", "skipped", "no_room")

    monday = SUNDAY + timedelta(days=1, hours=-10)
    assert await run("weekly", "weekly:2026-W42", monday) == "queued"
    asked = hub.asked[-1]
    assert asked["key"] == "weekly:2026-W42#2"
    assert "from Monday 12/10 to Sunday 18/10" in asked["prompt"]


async def test_sunday_always_asks_for_the_week(meter, api, hub) -> None:
    await weights(meter, SUNDAY)

    assert await run("weekly", "weekly:2026-W42", SUNDAY) == "queued"

    (asked,) = hub.asked
    assert asked["key"] == "weekly:2026-W42"
    prompt = asked["prompt"]
    assert "from Monday 12/10 to Sunday 18/10" in prompt
    assert 'topic "week:2026-w42"' in prompt
    assert 'kind "weekly"' in prompt
    assert "(None.)" in prompt


async def test_an_unread_insight_is_a_notification_until_it_is_read(api) -> None:
    from insights.main import as_role

    published = (await api.post("/tools/publish_insight", json=insight(), headers=WRITE)).json()[
        "content"
    ]["published"]

    async with as_role("mod_insights") as connection:
        before = await worker.notifications(connection)
    await api.post(f"/insights/{published['insight_id']}/read")
    async with as_role("mod_insights") as connection:
        after = await worker.notifications(connection)

    [one] = before
    assert one["kind"] == "insight"
    assert one["key"] == f"insight:{published['insight_id']}"
    assert one["href"] == f"/insights/insight/{published['insight_id']}"
    assert one["title"].startswith("Insights: Restaurants")
    assert after == []


def test_a_pass_is_looked_at_once_an_hour_per_person() -> None:
    worker.LOOKED.clear()
    assert worker.looking("ana", "morning:2026-10-13", clock=0)
    assert not worker.looking("ana", "morning:2026-10-13", clock=1800)
    assert worker.looking("luis", "morning:2026-10-13", clock=1800)
    assert worker.looking("ana", "morning:2026-10-13", clock=3600)
