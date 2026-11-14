from __future__ import annotations

from insights_world import insight, weekly

READ = {"x-arga-scopes": "insights:read"}
WRITE = {"x-arga-scopes": "insights:read insights:write"}


def call(api, name: str, arguments: dict, headers: dict = WRITE):
    return api.post(f"/tools/{name}", json=arguments, headers=headers)


async def content(api, name: str, arguments: dict, headers: dict = WRITE) -> dict:
    response = await call(api, name, arguments, headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


async def test_a_published_insight_reaches_the_inbox_unread(api) -> None:
    published = (await content(api, "publish_insight", insight()))["published"]

    inbox = (await api.get("/insights")).json()
    assert [one["id"] for one in inbox] == [published["insight_id"]]
    assert inbox[0]["read_at"] is None
    assert (await api.get("/badge")).json() == {"count": 1}


async def test_without_a_baseline_it_is_refused_saying_what_is_missing(api) -> None:
    figure = insight()["figures"][0]
    del figure["baseline"]

    response = await call(api, "publish_insight", insight(figures=[figure]))

    assert response.status_code == 422
    assert "baseline" in response.text
    assert (await api.get("/insights")).json() == []


async def test_without_an_action_or_what_it_affects_it_is_refused(api) -> None:
    assert (await call(api, "publish_insight", insight(action="Gasta menos"))).status_code == 422
    assert (await call(api, "publish_insight", insight(affects=""))).status_code == 422
    assert (await call(api, "publish_insight", insight(figures=[]))).status_code == 422


async def test_the_same_topic_with_the_same_figure_is_not_repeated(api) -> None:
    await content(api, "publish_insight", insight())

    again = await content(api, "publish_insight", insight(title="Otra vez restaurantes"))

    assert again["published"] is None
    assert "money.spend:restaurants" in again["note"]
    assert len((await api.get("/insights")).json()) == 1


async def test_the_same_topic_comes_back_when_its_figure_moves(api) -> None:
    await content(api, "publish_insight", insight())
    moved = insight()["figures"][0] | {"value": 520}

    again = await content(api, "publish_insight", insight(figures=[moved]))

    assert again["published"] is not None


async def test_the_weekly_summary_is_never_a_repetition(api) -> None:
    await content(api, "publish_insight", weekly())

    assert (await content(api, "publish_insight", weekly()))["published"] is not None


async def test_the_weekly_summary_brings_its_proposals_numbered(api) -> None:
    await content(api, "publish_insight", weekly(5))

    (found,) = (await content(api, "get_insights", {}, READ))["insights"]
    assert [one["number"] for one in found["proposals"]] == [1, 2, 3, 4, 5]
    assert found["proposals"][1]["what"].endswith("(proposal 2)")
    assert found["proposals"][1]["figure"]["baseline"] == 2
    assert found["proposals"][1]["how"].startswith("Shopping:")
    (inbox,) = (await api.get("/insights")).json()
    assert len(inbox["proposals"]) == 5


async def test_a_weekly_summary_without_three_to_seven_proposals_is_refused(api) -> None:
    for count in (0, 2, 8):
        response = await call(api, "publish_insight", weekly(count))
        assert response.status_code == 422, count
        assert "proposals" in response.text
    assert (await api.get("/insights")).json() == []


async def test_an_alert_does_not_bring_proposals(api) -> None:
    proposals = weekly()["proposals"]

    response = await call(api, "publish_insight", insight(proposals=proposals))

    assert response.status_code == 422
    (await content(api, "publish_insight", insight()))
    (alone,) = (await content(api, "get_insights", {}, READ))["insights"]
    assert "proposals" not in alone


async def test_publishing_with_only_the_read_scope_is_refused_by_postgres(api) -> None:
    response = await call(api, "publish_insight", insight(), headers=READ)

    assert response.status_code == 403


async def test_the_profile_and_past_insights_are_read_with_the_read_scope(api) -> None:
    await api.put("/profile", json={"name": "Txuri", "about": "Saving for a flat in 2027."})
    published = (await content(api, "publish_insight", insight()))["published"]
    await api.put(f"/insights/{published['insight_id']}/rating", json={"rating": "known"})

    profile = await content(api, "get_profile", {}, READ)
    past = (await content(api, "get_insights", {}, READ))["insights"]

    assert profile == {"name": "Txuri", "about": "Saving for a flat in 2027."}
    assert [(one["topic"], one["rating"], one["read"]) for one in past] == [
        ("money.spend:restaurants", "known", True)
    ]


async def test_claude_notes_the_rating_the_person_gives(api) -> None:
    published = (await content(api, "publish_insight", insight()))["published"]

    rated = await content(
        api, "rate_insight", {"insight_id": published["insight_id"], "rating": "useful"}
    )

    assert rated["rated"]["rating"] == "useful"
