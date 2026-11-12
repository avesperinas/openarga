from __future__ import annotations

from datetime import timedelta

from outings_world import TODAY

from outings import agenda

WRITE = {"x-arga-scopes": "outings:write"}
READ = {"x-arga-scopes": "outings:read"}


def found(title: str, days: int, town: str = "Pamplona", **extra) -> dict:
    return {
        "title": title,
        "starts_on": (TODAY + timedelta(days=days)).isoformat(),
        "category": "stage",
        "town": town,
        "link": "https://prensa.example/noticia",
        **extra,
    }


async def add(api, *events: dict) -> list[str]:
    said = await api.post("/tools/add_events", json={"events": list(events)}, headers=WRITE)
    assert said.status_code == 200, said.text
    return [one["event_id"] for one in said.json()["content"]["events"]]


async def explore(api, **params) -> dict:
    got = await api.get("/explore", params=params)
    assert got.status_code == 200, got.text
    return got.json()


def titles(answer: dict) -> list[str]:
    return [one["title"] for one in answer["events"]]


def test_the_zone_is_pamplona_and_its_comarca_or_the_rest() -> None:
    assert agenda.zone("Pamplona/Iruña") == "pamplona"
    assert agenda.zone("Villava/Atarrabia") == "pamplona"
    assert agenda.zone("Barañáin") == "pamplona"
    assert agenda.zone("Cintruénigo") == "navarra"
    assert agenda.zone(None) == "navarra"


async def test_a_festival_is_one_event_with_its_programme(api) -> None:
    [event_id] = await add(
        api,
        found(
            "Fiesta Sintética de la Verdura",
            4,
            town="Villa Sintética",
            category="eat",
            ends_on=(TODAY + timedelta(days=6)).isoformat(),
            programme=["Sáb, 12:00 · Concurso de tortillas", "Dom, 13:00 · Degustación"],
            highlight=True,
        ),
    )

    event = (await api.get(f"/events/{event_id}")).json()
    assert event["programme"] == [
        "Sáb, 12:00 · Concurso de tortillas",
        "Dom, 13:00 · Degustación",
    ]
    assert event["highlight"] is True and event["zone"] == "navarra"
    assert titles(await explore(api, q="tortillas")) == ["Fiesta Sintética de la Verdura"]


async def test_the_search_ignores_accents_and_takes_the_start_of_words(api) -> None:
    await add(
        api,
        found("Concierto de Órgano Sintético", 3, venue="Catedral"),
        found("Semana Sintética de la Croqueta", 5, category="eat"),
    )

    assert titles(await explore(api, q="organo")) == ["Concierto de Órgano Sintético"]
    assert titles(await explore(api, q="CROQ")) == ["Semana Sintética de la Croqueta"]
    assert titles(await explore(api, q="catedral concierto")) == ["Concierto de Órgano Sintético"]
    assert titles(await explore(api, q="nada parecido")) == []


async def test_since_keeps_only_what_arrived_from_that_day(api) -> None:
    from sqlalchemy import text

    from outings.main import as_app

    old_one, new_one = found("Concierto sintético viejo", 3), found("Concierto sintético nuevo", 4)
    [old, new] = await add(api, old_one, new_one)
    async with as_app() as connection:
        await connection.execute(
            text(
                "update outings.outings_event set first_seen = now() - interval '10 days'"
                " where id = cast(:id as uuid)"
            ),
            {"id": old},
        )
        madrid = text("select (now() at time zone 'Europe/Madrid')::date")
        today = (await connection.execute(madrid)).scalar_one()

    fresh = await explore(api, since=(today - timedelta(days=2)).isoformat(), sort="best")
    assert titles(fresh) == ["Concierto sintético nuevo"]
    assert fresh["events"][0]["id"] == new
    everything = set(titles(await explore(api)))
    assert everything >= {"Concierto sintético viejo", "Concierto sintético nuevo"}


async def test_best_puts_pamplona_and_what_is_big_first(api) -> None:
    await add(
        api,
        found("Lejos y pequeño", 2, town="Villa Sintética"),
        found("Lejos y grande", 3, town="Villa Sintética", highlight=True),
        found("Aquí y pequeño", 4),
        found("Aquí y grande", 5, highlight=True),
    )

    best = await explore(api, sort="best")
    assert titles(best) == ["Aquí y grande", "Lejos y grande", "Aquí y pequeño", "Lejos y pequeño"]
    by_date = await explore(api)
    assert titles(by_date)[0] == "Lejos y pequeño"
    assert titles(await explore(api, zone="pamplona")) == ["Aquí y pequeño", "Aquí y grande"]


async def test_what_you_like_goes_up(api) -> None:
    await add(api, found("Concierto Sintético de Jazz", 9), found("Otra Cosa Sintética", 2))
    await api.post("/interests", json={"kind": "like", "term": "Jazz"})

    assert titles(await explore(api, sort="best"))[0] == "Concierto Sintético de Jazz"
    assert "Jazz" in (await api.get("/agenda/prompt")).json()["prompt"]


async def test_dismissed_and_muted_do_not_show_unless_they_are_yours(api) -> None:
    dismissed, muted, kept, saved = await add(
        api,
        found("Congreso Sintético de Líderes", 2),
        found("Charla Sintética en la Sala Equis", 3, venue="Sala Equis"),
        found("Concierto Sintético", 4),
        found("Recital Sintético en la Sala Equis", 5, venue="Sala Equis"),
    )
    await api.post(f"/events/{saved}/save")
    hid = await api.post("/tools/hide_events", json={"event_ids": [dismissed]}, headers=WRITE)
    assert hid.json()["content"] == {"hidden": 1, "not_found": []}
    added = await api.post(
        "/tools/add_interest", json={"kind": "mute", "term": "sala equis"}, headers=WRITE
    )
    assert added.status_code == 200, added.text

    assert set(titles(await explore(api))) == {
        "Concierto Sintético",
        "Recital Sintético en la Sala Equis",
    }
    week = (await api.post("/tools/find_events", json={"when": "week"}, headers=READ)).json()
    assert {one["event_id"] for one in week["content"]["events"]} == {kept, saved}
    await add(api, found("Congreso Sintético de Líderes", 2, summary="Otra versión."))
    assert dismissed not in {one["id"] for one in (await explore(api))["events"]}
    await api.put(f"/events/{dismissed}/dismiss", params={"on": "false"})
    await api.post(
        "/tools/remove_interest", json={"kind": "mute", "term": "Sala Equis"}, headers=WRITE
    )
    assert len((await explore(api))["events"]) == 4
    assert muted in {one["id"] for one in (await explore(api))["events"]}


async def test_mine_is_only_what_you_saved_or_sent_to_planner(api) -> None:
    saved, sent, _other = await add(
        api, found("Guardado Sintético", 3), found("En Planner Sintético", 6), found("Otro", 8)
    )
    await api.post(f"/events/{saved}/save")
    await api.put(f"/events/{sent}/calendar", params={"on": "true"})

    got = await api.get(
        "/mine",
        params={"from": TODAY.isoformat(), "to": (TODAY + timedelta(days=30)).isoformat()},
    )

    assert got.status_code == 200, got.text
    assert [one["id"] for one in got.json()["events"]] == [saved, sent]


async def test_find_events_and_the_brief_are_tools_for_claude(api) -> None:
    await add(api, found("Festival Sintético de Cine", 20, highlight=True))
    await api.post("/interests", json={"kind": "mute", "term": "congreso"})

    got = await api.post(
        "/tools/find_events", json={"query": "cine", "when": "quarter"}, headers=READ
    )
    brief = await api.post("/tools/get_agenda_brief", json={}, headers=READ)

    [event] = got.json()["content"]["events"]
    assert event["title"] == "Festival Sintético de Cine" and event["highlight"] is True
    assert event["zone"] == "pamplona"
    said = brief.json()["content"]["brief"]
    assert "add_events" in said and "congreso" in said


async def test_interests_are_listed_and_not_repeated(api) -> None:
    await api.post("/interests", json={"kind": "like", "term": "Jazz"})
    await api.post("/interests", json={"kind": "like", "term": "jazz"})
    listed = (await api.get("/interests")).json()

    assert [(one["kind"], one["term"]) for one in listed] == [("like", "jazz")]
    removed = await api.delete(f"/interests/{listed[0]['id']}")
    assert removed.status_code == 200
    assert (await api.get("/interests")).json() == []
