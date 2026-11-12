from __future__ import annotations

READ = {"x-arga-scopes": "insights:read"}
WRITE = {"x-arga-scopes": "insights:read insights:write"}


async def tool(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await api.post(f"/tools/{name}", json=arguments, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def answer(api, key: str, **given) -> dict:
    response = await api.post(f"/onboarding/{key}", json={"answer": given or None})
    assert response.status_code == 200, response.text
    return response.json()


async def test_it_starts_with_your_themes_and_without_the_outside_one(api) -> None:
    started = (await api.get("/onboarding")).json()

    first = started["questions"][0]
    assert started["done"] is False and started["answered"] == 0
    assert first["bank_key"] == "start.families" and first["kind"] == "many"
    keys = [one["value"] for one in first["options"]]
    assert "historia" in keys and "fuera" not in keys


async def test_choosing_themes_raises_them_and_the_favourite_only_offers_those(api) -> None:
    after = await answer(api, "start.families", values=["historia", "ciencia", "nada"])

    favourite = after["questions"][0]
    assert favourite["bank_key"] == "start.favourite"
    assert [one["value"] for one in favourite["options"]] == ["historia", "ciencia"]

    await answer(api, "start.favourite", values=["ciencia"])
    tastes = (await api.get("/tastes")).json()
    weights = {one["key"]: one["weight"] for one in tastes["families"]}
    assert (weights["historia"], weights["ciencia"], weights["economia"]) == (2, 3, 1)
    topics = {one["label"]: one for one in tastes["traits"] if one["facet"] == "topic"}
    assert topics["Ciencia y universo"]["stance"] == 2
    assert topics["Historia"]["status"] == "confirmed"
    assert topics["Historia"]["source"] == "answered"


async def test_a_skipped_question_does_not_come_back(api) -> None:
    skipped = await answer(api, "start.families")

    assert all(one["bank_key"] != "start.families" for one in skipped["questions"])
    assert skipped["answered"] == 1


async def test_the_level_is_only_asked_when_you_learn_a_language(api) -> None:
    keys = [one["bank_key"] for one in (await api.get("/onboarding")).json()["questions"]]
    assert "start.level" not in keys

    after = await answer(api, "start.learning", values=["de"])
    assert "start.level" in [one["bank_key"] for one in after["questions"]]
    await answer(api, "start.level", values=["B1"])
    await answer(api, "start.time", values=["21:30"])
    await answer(api, "start.minutes", values=["10"])

    settings = (await api.get("/tastes")).json()["settings"]
    assert (settings["pill_language"], settings["pill_level"]) == ("de", "B1")
    assert (settings["pill_time"], settings["pill_minutes"]) == ("21:30", 10)


async def test_what_you_loved_and_what_you_avoid_are_said_by_you(api) -> None:
    await answer(api, "start.loved", text="Dune\nCosmos, de Carl Sagan; The Wire")
    await answer(api, "start.avoid", text="fútbol")

    traits = (await api.get("/tastes")).json()["traits"]
    works = sorted(one["label"] for one in traits if one["facet"] == "work")
    avoid = [one for one in traits if one["facet"] == "avoid"]
    assert works == ["Cosmos", "Dune", "The Wire", "de Carl Sagan"]
    assert avoid[0]["label"] == "fútbol" and avoid[0]["stance"] == -2
    assert all(one["source"] == "said" and one["status"] == "confirmed" for one in traits)


async def test_outside_your_zone_can_be_switched_off(api) -> None:
    await answer(api, "start.outside", values=["never"])

    families = (await api.get("/tastes")).json()["families"]
    assert next(one for one in families if one["key"] == "fuera")["weight"] == 0


async def test_claude_only_proposes_and_what_you_reject_does_not_come_back(api) -> None:
    proposed = await tool(
        api,
        "propose_trait",
        {
            "facet": "genre",
            "label": "Fantasía épica",
            "stance": 2,
            "evidence": "Seis novelas del género, media 4,2",
        },
    )
    trait = proposed["trait"]
    assert trait["status"] == "proposed"

    rejected = (await api.put(f"/traits/{trait['trait_id']}", json={"status": "rejected"})).json()
    again = await tool(
        api,
        "propose_trait",
        {"facet": "genre", "label": "fantasia  EPICA", "evidence": "Otra vez lo mismo"},
    )

    assert rejected["status"] == "rejected"
    assert again["trait"]["status"] == "rejected"
    assert "no vuelve" in again["note"]


async def test_what_the_person_says_is_confirmed_and_can_be_forgotten(api) -> None:
    noted = await tool(api, "note_taste", {"facet": "creator", "label": "Ursula K. Le Guin"})
    added = (await api.post("/traits", json={"facet": "topic", "label": "Física"})).json()

    assert noted["trait"]["status"] == "confirmed"
    assert added["status"] == "confirmed" and added["source"] == "said"
    assert (await api.delete(f"/traits/{added['id']}")).status_code == 204
    labels = [one["label"] for one in (await api.get("/tastes")).json()["traits"]]
    assert labels == ["Ursula K. Le Guin"]


QUESTION = {
    "kind": "one",
    "text": "¿Prefieres sagas largas o novelas que se cierran?",
    "why": "Has terminado varias sagas este año",
    "options": [{"value": "saga", "label": "Sagas"}, {"value": "one", "label": "Que se cierren"}],
    "topic": "gusto.longitud",
}


async def test_one_question_waits_at_a_time_and_the_answer_reaches_the_next_pass(api) -> None:
    asked = await tool(api, "ask_question", QUESTION)
    second = await tool(api, "ask_question", QUESTION | {"topic": "gusto.otra"})
    today = (await api.get("/today")).json()

    assert asked["asked"]["text"] == QUESTION["text"]
    assert second["asked"] is None and "esperando" in second["note"]
    question = today["question"]
    assert question["why"] == QUESTION["why"]

    answered = (
        await api.post(f"/questions/{question['id']}/answer", json={"answer": {"values": ["saga"]}})
    ).json()
    assert answered["answered_at"] is not None
    assert (await api.get("/today")).json()["question"] is None


async def test_confirming_a_trait_by_question_confirms_it(api) -> None:
    trait = (
        await tool(
            api,
            "propose_trait",
            {"facet": "format", "label": "Podcasts largos", "evidence": "Escucha en el coche"},
        )
    )["trait"]
    asked = await tool(
        api,
        "ask_question",
        {
            "kind": "confirm",
            "text": "¿Te gustan los podcasts largos?",
            "why": "Lo he visto en tus datos",
            "topic": "rasgo.podcasts-largos",
            "trait_id": trait["trait_id"],
        },
    )

    question_id = asked["asked"]["question_id"]
    await api.post(f"/questions/{question_id}/answer", json={"answer": {"value": "yes"}})

    traits = (await api.get("/tastes")).json()["traits"]
    assert traits[0]["status"] == "confirmed"


async def test_never_means_never_and_a_topic_is_not_asked_twice(api) -> None:
    first = await tool(api, "ask_question", QUESTION)
    await api.post(f"/questions/{first['asked']['question_id']}/answer", json={"answer": None})
    await api.put("/settings", json={"questions": "daily"})

    repeated = await tool(api, "ask_question", QUESTION)
    await api.put("/settings", json={"questions": "never"})
    never = await tool(api, "ask_question", QUESTION | {"topic": "otra.cosa"})

    assert repeated["asked"] is None
    assert never["asked"] is None and "nunca" in never["note"]


async def test_themes_and_sources_are_yours(api) -> None:
    await api.get("/tastes")
    changed = (await api.put("/families/historia", json={"weight": 0})).json()
    created = (
        await api.post(
            "/families",
            json={"name": "Ajedrez", "themes": "aperturas, historia", "glyph": "target"},
        )
    ).json()
    source = (
        await api.post(
            "/sources",
            json={
                "family_key": created["key"],
                "name": "Una revista de ajedrez",
                "kind": "magazine",
                "url": "https://example.org/ajedrez",
            },
        )
    ).json()
    hidden_id = next(
        one["id"]
        for one in (await api.get("/tastes")).json()["sources"]
        if one["family_key"] == "historia"
    )
    hidden = (await api.put(f"/sources/{hidden_id}", json={"hidden": True})).json()

    assert changed["weight"] == 0
    assert created["key"] == "ajedrez" and created["weight"] == 2
    assert source["builtin"] is False
    assert hidden["hidden"] is True
    assert (await api.put("/families/nada", json={"weight": 1})).status_code == 404


async def test_your_tastes_are_readable_by_claude(api) -> None:
    await tool(api, "note_taste", {"facet": "creator", "label": "Ursula K. Le Guin"})

    read = await tool(api, "get_tastes", {}, READ)

    assert read["traits"][0]["label"] == "Ursula K. Le Guin"
    assert any(one["key"] == "historia" for one in read["families"])
    assert read["settings"]["pill_minutes"] == 15
