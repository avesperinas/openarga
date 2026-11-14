from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from insights_taste_world import facts, pill
from sqlalchemy import text

from arga_widgets import validate
from insights import craft, passes, pills, records, tastes, worker
from insights.main import as_role

MADRID = ZoneInfo("Europe/Madrid")

READ = {"x-arga-scopes": "insights:read"}
WRITE = {"x-arga-scopes": "insights:read insights:write"}
TUESDAY = datetime(2026, 11, 10, 8, 40, tzinfo=MADRID)


class Hub:
    def __init__(self) -> None:
        self.asked: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/capabilities/claude.run"
        self.asked.append(json.loads(request.content))
        return httpx.Response(200, json={"outcome": "queued", "run": "r", "repeated": False})


@pytest.fixture
def hub(monkeypatch) -> Hub:
    fake = Hub()
    monkeypatch.setattr(passes, "transport", lambda: httpx.MockTransport(fake))
    return fake


async def tool(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await api.post(f"/tools/{name}", json=arguments, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def run(kind: str, key: str, now: datetime) -> str | None:
    async with as_role("mod_insights") as connection:
        return await craft.run(connection, kind, key, now, random.Random(1))


def today_key() -> str:
    return f"pill:{datetime.now(MADRID).date().isoformat()}"


def test_the_pill_is_asked_a_while_before_your_time_and_picks_on_friday_evening() -> None:
    settings = tastes.Settings(pill_time="09:00")

    early = craft.due(TUESDAY.replace(hour=8, minute=20), settings, True)
    on_time = craft.due(TUESDAY, settings, True)
    friday = craft.due(datetime(2026, 11, 13, 17, 30, tzinfo=MADRID), settings, True)
    first = craft.due(TUESDAY, settings, False)
    off = craft.due(TUESDAY, tastes.Settings(pill_on=False), True)

    assert early == []
    assert on_time == [("pill", "pill:2026-11-10")]
    assert ("picks", "picks:2026-W46") in friday
    assert ("profile", "profile:first") in first
    assert off == []


async def test_the_daily_pass_asks_for_a_pill_with_substance_and_web_reading(api, hub) -> None:
    await api.post("/onboarding/start.families", json={"answer": {"values": ["science"]}})
    await api.post("/onboarding/start.favourite", json={"answer": {"values": ["science"]}})

    outcome = await run("pill", "pill:2026-11-10", TUESDAY)
    again = await run("pill", "pill:2026-11-10", TUESDAY)

    assert (outcome, again) == ("queued", None)
    asked = hub.asked[0]
    assert asked["key"] == "pill:2026-11-10"
    assert set(asked["tools"]) == {"WebFetch", "WebSearch"}
    prompt = asked["prompt"]
    assert "Always with substance" in prompt and "never about the person or their figures" in prompt
    assert "insights_publish_pill" in prompt and "insights_publish_facts" in prompt
    assert 'run_key` "pill:2026-11-10"' in prompt
    assert "Science and the universe, weight 3 of 3" in prompt


async def test_a_pill_that_already_arrived_is_not_asked_again(api, hub) -> None:
    key = today_key()
    await run("pill", key, datetime.now(MADRID))
    await tool(api, "publish_pill", pill(key))
    async with as_role("mod_insights") as connection:
        await connection.execute(text("update insights.insights_craft_run set outcome = 'refused'"))

    assert await run("pill", key, datetime.now(MADRID)) == "quiet"


async def test_in_the_language_you_learn_once_a_week(api, hub) -> None:
    await api.put("/settings", json={"pill_language": "de", "pill_level": "B1"})
    saturday = datetime(2026, 11, 14, 9, 0, tzinfo=MADRID)

    await run("pill", "pill:2026-11-14", saturday)

    assert "Today it is in German" in hub.asked[0]["prompt"]
    assert "at level B1" in hub.asked[0]["prompt"]


async def test_a_published_pill_is_today_and_goes_to_the_notes(api, hub) -> None:
    key = today_key()
    await run("pill", key, datetime.now(MADRID))

    published = await tool(api, "publish_pill", pill(key))
    day = datetime.now(MADRID).date().isoformat()
    added = await tool(api, "publish_facts", facts(day))
    today = (await api.get("/today")).json()

    assert published["published"]["headline"] == "The column that broke Sparta"
    assert added["published"] == 5
    assert today["pill"]["topic"] == "The battle of Leuctra"
    assert len(today["facts"]) == 5
    assert (await api.get("/badge")).json() == {"count": 1}
    async with as_role("mod_insights_read") as connection:
        built = await records.build(connection)
    note = next(one for one in built if one["kind"] == "Pill")
    assert note["folder"] == "Pills"
    assert "To tell" in note["body"] and "Facts of the day" in note["body"]


async def test_the_pill_must_have_the_length_asked_a_theme_of_yours_and_be_new(api, hub) -> None:
    key = today_key()
    await run("pill", key, datetime.now(MADRID))
    short = pill(key, sections=[{"title": "Una", "text": "x " * 50}] * 3)

    too_short = await tool(api, "publish_pill", short)
    unknown = await tool(api, "publish_pill", pill(key, family_key="cocina"))
    no_order = await tool(api, "publish_pill", pill("pill:2020-01-01"))
    two_branches = await api.post(
        "/tools/publish_pill", json=pill(key, branches=pill(key)["branches"][:2]), headers=WRITE
    )

    assert too_short["published"] is None and "words" in too_short["note"]
    assert unknown["published"] is None and "their topics" in unknown["note"]
    assert no_order["published"] is None and "no task" in no_order["note"]
    assert two_branches.status_code == 422


async def test_repeated_facts_are_not_given_twice(api) -> None:
    day = datetime.now(MADRID).date().isoformat()
    await api.get("/tastes")

    first = await tool(api, "publish_facts", facts(day))
    second = await tool(api, "publish_facts", facts(day, 4))

    assert first["published"] == 5
    assert second["published"] == 0 and "not repeated" in second["note"]


async def test_reading_and_reacting(api, hub) -> None:
    key = today_key()
    await run("pill", key, datetime.now(MADRID))
    pill_id = (await tool(api, "publish_pill", pill(key)))["published"]["pill_id"]

    read = (await api.post(f"/pills/{pill_id}/read")).json()
    liked = (await api.put(f"/pills/{pill_id}/reaction", json={"reaction": "interested"})).json()
    history = (await api.get("/pills")).json()
    seen = await tool(api, "get_pills", {}, READ)

    assert read["read_at"] is not None and liked["reaction"] == "interested"
    assert history[0]["id"] == pill_id
    assert seen["pills"][0]["reaction"] == "interested"
    assert (await api.get("/today")).json()["streak"] == 1


async def test_surprise_me_and_a_branch_arrive_linked_with_a_daily_cap(api, hub) -> None:
    key = today_key()
    await run("pill", key, datetime.now(MADRID))
    parent = (await tool(api, "publish_pill", pill(key)))["published"]["pill_id"]

    asked = (
        await api.post(
            "/pills/more",
            json={"origin": "branch", "parent_id": parent, "branch": "Epaminondas"},
        )
    ).json()
    assert asked["state"] == "waiting" and asked["kind"] == "more"
    prompt = hub.asked[-1]["prompt"]
    assert 'It is a branch of the pill "The column that broke Sparta"' in prompt

    child = await tool(
        api, "publish_pill", pill(asked["key"], topic="Epaminondas", headline="El general tebano")
    )
    ready = (await api.get(f"/asks/{asked['id']}")).json()
    opened = (await api.get(f"/pills/{parent}")).json()

    assert ready["state"] == "ready" and ready["pill_id"] == child["published"]["pill_id"]
    assert opened["children"][0]["topic"] == "Epaminondas"
    branch = (await api.get(f"/pills/{ready['pill_id']}")).json()
    assert branch["pill"]["depth"] == 1 and branch["parent"]["id"] == parent

    for _ in range(2):
        surprise = await api.post("/pills/more", json={"origin": "surprise"})
        assert surprise.status_code == 201, surprise.text
    capped = await api.post("/pills/more", json={"origin": "surprise"})
    assert capped.status_code == 429


def families(**weights: int) -> list[tastes.Family]:
    return [
        one.model_copy(update={"weight": weights.get(one.key, 1)})
        for one in tastes.default_families()
    ]


def test_a_theme_switched_off_never_comes_and_a_heavy_one_comes_more() -> None:
    now = datetime(2026, 11, 10, 9, tzinfo=UTC)
    rng = random.Random(3)
    taken: list[pills.Taken] = []
    counts: dict[str, int] = {}
    weights = {"history": 3, "geopolitics": 0, "outside": 0}
    for day in range(60):
        chosen = pills.choose(families(**weights), taken, now + timedelta(days=day), rng)
        counts[chosen.key] = counts.get(chosen.key, 0) + 1
        taken.insert(
            0,
            pills.Taken(family_key=chosen.key, created_at=now + timedelta(days=day), reaction=None),
        )

    assert "geopolitics" not in counts and "outside" not in counts
    assert counts["history"] == max(counts.values())


def test_outside_your_zone_comes_once_a_week_if_you_want_it() -> None:
    now = datetime(2026, 11, 10, 9, tzinfo=UTC)
    rng = random.Random(4)
    taken: list[pills.Taken] = []
    picked = []
    for day in range(28):
        chosen = pills.choose(families(outside=2), taken, now + timedelta(days=day), rng)
        picked.append(chosen.key)
        taken.insert(
            0,
            pills.Taken(family_key=chosen.key, created_at=now + timedelta(days=day), reaction=None),
        )

    assert picked.count("outside") == 4


def test_the_streak_forgives_one_day_a_week() -> None:
    today = date(2026, 11, 10)
    days = {today - timedelta(days=n) for n in range(0, 10) if n != 4}

    assert pills.streak(days, today) == 9
    assert pills.streak(set(), today) == 0
    assert pills.streak({today - timedelta(days=1)}, today) == 1


async def test_the_pill_notifies_at_your_time_and_the_widget_shows_it(api, hub) -> None:
    key = today_key()
    await run("pill", key, datetime.now(MADRID))
    await api.put("/settings", json={"pill_time": "00:00"})
    await tool(api, "publish_pill", pill(key))
    await tool(api, "publish_facts", facts(datetime.now(MADRID).date().isoformat()))

    async with as_role("mod_insights_read") as connection:
        found = await worker.notifications(connection)
    widget = (await api.get("/widgets/today")).json()

    assert [one["kind"] for one in found] == ["pill"]
    assert found[0]["href"].startswith("/insights/pill/")
    assert widget["state"] == "ready"
    validate("list", widget["body"], "ready")
    assert widget["body"]["rows"][0]["label"] == "The column that broke Sparta"
