from __future__ import annotations

from datetime import timedelta

from outings_world import TODAY
from sqlalchemy import text

from outings import agenda, foryou

WRITE = {"x-arga-scopes": "outings:write"}
READ = {"x-arga-scopes": "outings:read"}


def found(title: str, days: int, town: str = "Villa Sintética", **extra) -> dict:
    return {
        "title": title,
        "starts_on": (TODAY + timedelta(days=days)).isoformat(),
        "category": "stage",
        "town": town,
        "link": "https://prensa.example/noticia",
        **extra,
    }


async def call(api, name: str, body: dict, headers: dict = WRITE):
    answer = await api.post(f"/tools/{name}", json=body, headers=headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["content"]


async def add(api, *events: dict) -> list[str]:
    said = await call(api, "add_events", {"events": list(events)})
    return [one["event_id"] for one in said["events"]]


async def built() -> list[dict]:
    from outings.main import as_app

    async with as_app() as connection:
        return await foryou.build(connection)


async def arrived_on() -> str:
    from outings.main import as_app

    async with as_app() as connection:
        query = text(
            "select (max(first_seen) at time zone 'Europe/Madrid')::date from outings.outings_event"
        )
        return (await connection.execute(query)).scalar_one().isoformat()


async def test_what_you_like_what_is_big_nearby_and_what_names_a_wish_come_with_their_reason(
    api,
) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await call(api, "add_wish", {"kind": "getaway", "name": "Bardenas Sintéticas"})
    await add(
        api,
        found("Noche de jazz sintético", 3),
        found("Feria Sintética de Otoño", 5, town="Pamplona", highlight=True),
        found("Ruta por las Bardenas Sintéticas", 8),
        found("Charla cualquiera", 4),
    )

    picked = (await api.get("/foryou")).json()

    reasons = {one["event"]["title"]: one["reasons"] for one in picked}
    assert reasons == {
        "Noche de jazz sintético": ["Te interesa «jazz»"],
        "Feria Sintética de Otoño": ["De lo grande en la Comarca de Pamplona"],
        "Ruta por las Bardenas Sintéticas": [
            "Cerca de «Bardenas Sintéticas», que está en tus Ganas"
        ],
    }


async def test_what_you_set_aside_or_already_saved_is_not_for_you(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    aside, saved = await add(api, found("Jazz apartado", 3), found("Jazz guardado", 4))
    await call(api, "hide_events", {"event_ids": [aside]})
    await call(api, "save_event", {"event_id": saved})

    assert (await api.get("/foryou")).json() == []


async def test_one_notice_per_day_with_the_title_or_the_count(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await add(api, found("Jazz sintético uno", 3))

    [one] = [notice for notice in await built() if notice["kind"] == "for_you"]
    assert one["title"] == "Te puede gustar: Jazz sintético uno"
    assert one["key"] == f"for_you:{await arrived_on()}"
    assert one["href"] == f"/outings/explorar?nuevo={await arrived_on()}"
    assert "Te interesa «jazz»" in one["body"]

    await add(api, found("Jazz sintético dos", 6))
    [both] = [notice for notice in await built() if notice["kind"] == "for_you"]
    assert both["title"] == "2 planes para ti"
    assert both["key"] == one["key"]


async def test_the_weekend_comes_on_thursday(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    friday, _ = agenda.window("weekend", TODAY)
    await add(api, found("Jazz del finde", (friday - TODAY).days))

    [weekend] = [notice for notice in await built() if notice["kind"] == "weekend"]
    assert weekend["key"] == f"weekend:{friday.isoformat()}"
    assert weekend["href"] == "/outings/explorar?cuando=weekend"
    assert weekend["at"].startswith((friday - timedelta(days=1)).isoformat())
    assert weekend["body"] == "Jazz del finde"


async def test_what_you_saved_and_starts_tomorrow_warns_the_day_before(api) -> None:
    [event_id] = await add(api, found("Concierto guardado", 1))
    saved = await call(api, "save_event", {"event_id": event_id})

    [soon] = [notice for notice in await built() if notice["kind"] == "saved_soon"]
    assert soon["title"] == "Mañana empieza Concierto guardado"
    assert soon["href"] == f"/outings/ganas/{saved['wish_id']}"


async def test_claude_asks_for_what_you_may_like(api) -> None:
    await call(api, "add_interest", {"kind": "like", "term": "jazz"})
    await add(api, found("Jazz sintético", 3), found("Teatro sintético", 4))

    answer = await call(api, "find_events", {"for_you": True}, READ)

    assert answer["total"] == 1
    [one] = answer["events"]
    assert one["title"] == "Jazz sintético" and one["why"] == ["Te interesa «jazz»"]
