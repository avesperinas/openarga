from __future__ import annotations

from datetime import timedelta

from goals import tools
from goals.common import today

WRITE = {"x-arga-scopes": "goals:write"}
READ = {"x-arga-scopes": "goals:read"}


async def call(api, name: str, arguments: dict, scopes: dict = WRITE) -> dict:
    response = await api.post(f"/tools/{name}", json=arguments, headers=scopes)
    assert response.status_code == 200, response.text
    return response.json()["content"]


def test_the_manifest_declares_every_tool_and_no_more() -> None:
    from pathlib import Path

    import yaml

    manifest = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "manifest.yaml").read_text(encoding="utf-8")
    )
    declared = {tool["name"]: tool["scope"] for tool in manifest["tools"]}
    assert set(declared) == set(tools.TOOLS)
    assert {name for name, scope in declared.items() if scope == "goals:read"} == {
        "get_categories",
        "find_tasks",
        "get_goals",
        "get_goal",
        "list_metrics",
    }


def test_the_scope_decides_the_role() -> None:
    assert tools.role_for_scopes({"goals:write", "goals:read"}) == "mod_goals"
    assert tools.role_for_scopes({"goals:read"}) == "mod_goals_read"
    assert tools.role_for_scopes({"arca:write"}) is None


async def test_claude_adds_a_weekly_task_told_in_words(api) -> None:
    first = today() + timedelta(days=(1 - today().weekday()) % 7 or 7)
    created = await call(
        api,
        "add_task",
        {
            "title": "Take the bins out",
            "category": "home",
            "due_on": first.isoformat(),
            "repeat": {"freq": "weekly", "by_day": [{"weekday": "TU"}]},
        },
    )
    assert created["category"] == "Home"
    assert created["repeats"] == "every week, on Tuesday"

    done = await call(api, "complete_task", {"task_id": created["task_id"]})
    assert done["done"]["status"] == "done"
    assert done["next"]["due_on"] == (first + timedelta(days=7)).isoformat()

    listed = (await api.get("/tasks")).json()
    assert [(one["title"], one["due_on"]) for one in listed] == [
        ("Take the bins out", (first + timedelta(days=7)).isoformat())
    ]


async def test_reading_with_the_reader_role(api) -> None:
    await call(
        api,
        "add_task",
        {
            "title": "Send the invoice",
            "category": "Work",
            "due_on": (today() - timedelta(days=1)).isoformat(),
        },
    )
    await call(api, "add_task", {"title": "Read about indexes", "category": "Personal"})

    due = await call(api, "find_tasks", {"due_until": today().isoformat()}, READ)
    assert [(one["title"], one["status"]) for one in due["tasks"]] == [
        ("Send the invoice", "overdue")
    ]

    found = await call(api, "find_tasks", {"query": "indexes"}, READ)
    assert [one["title"] for one in found["tasks"]] == ["Read about indexes"]

    counted = await call(api, "get_categories", {}, READ)
    assert {one["name"]: one["overdue"] for one in counted["categories"]} == {
        "Work": 1,
        "Home": 0,
        "Personal": 0,
    }


async def test_the_reader_role_cannot_add(api) -> None:
    await call(api, "get_categories", {}, WRITE)
    refused = await api.post(
        "/tools/add_task", json={"title": "X", "category": "Home"}, headers=READ
    )
    assert refused.status_code == 403


async def test_an_unknown_category_says_which_there_are(api) -> None:
    answer = await call(api, "add_task", {"title": "X", "category": "Errands"})
    assert (
        answer["error"]
        == "there is no category 'Errands'. The ones there are: Work, Home, Personal"
    )
    created = await call(api, "add_category", {"name": "Errands"})
    assert created == {"name": "Errands", "hue": 3}
    added = await call(api, "add_task", {"title": "Pick up the parcel", "category": "errands"})
    assert added["category"] == "Errands"


async def test_a_tool_that_fails_leaves_nothing_behind(api, schema) -> None:
    from sqlalchemy import text

    answer = await call(api, "add_task", {"title": "X", "category": "Errands"})
    assert "Errands" in answer["error"]
    async with schema.begin() as connection:
        seeded = await connection.scalar(text("select count(*) from goals.goals_category"))
    assert seeded == 0


async def test_update_moves_and_clears(api) -> None:
    created = await call(
        api,
        "add_task",
        {
            "title": "Review the PR",
            "category": "Work",
            "due_on": today().isoformat(),
            "due_time": "10:00",
        },
    )
    moved = await call(
        api,
        "update_task",
        {"task_id": created["task_id"], "category": "Personal", "due_time": None},
    )
    assert moved["category"] == "Personal" and moved["due_time"] is None
    assert moved["due_on"] == today().isoformat()


async def test_claude_sets_a_goal_marks_it_and_answers_how_it_goes(api) -> None:
    created = await call(
        api,
        "create_goal",
        {
            "title": "Read 20 minutes",
            "kind": "periodic",
            "period": "day",
            "days_per_week": 5,
            "category": "learning",
        },
    )
    assert created["category"] == "Learning" and created["today_met"] is False

    marked = await call(api, "check_goal", {"goal_id": created["goal_id"], "done": True})
    assert marked["today_met"] is True and marked["today_marked_by_hand"] is True

    how = await call(api, "get_goals", {}, READ)
    app = (await api.get("/goals")).json()
    assert [(one["title"], one["today_met"]) for one in how["goals"]] == [
        (one["title"], one["today_met"]) for one in app
    ]
    assert how["goals"][0]["this_week"]["done"] == app[0]["week_count"]


async def test_a_dated_goal_by_hand_then_closed_and_deleted_by_title(api) -> None:
    created = await call(
        api,
        "create_goal",
        {
            "title": "Bajar a 80 kg",
            "kind": "dated",
            "direction": "at_most",
            "start_value": 85,
            "target": 80,
            "start_on": (today() - timedelta(days=30)).isoformat(),
            "due_on": (today() + timedelta(days=30)).isoformat(),
        },
    )
    logged = await call(api, "check_goal", {"goal_id": created["goal_id"], "value": 82})
    assert logged["current"] == 82 and logged["pace"] == "ahead"

    history = await call(api, "get_goal", {"goal_id": created["goal_id"]}, READ)
    assert history["history"][-1]["value"] == 82 and history["history"][-1]["by_hand"] is True

    changed = await call(api, "update_goal", {"goal_id": created["goal_id"], "target": 79})
    assert changed["target"] == 79

    gone = await call(api, "close_goal", {"goal_id": created["goal_id"], "outcome": "abandoned"})
    assert gone["status"] == "abandoned"

    wrong = await call(api, "delete_goal", {"goal_id": created["goal_id"], "title": "Go down"})
    assert "does not match" in wrong["error"]
    done = await call(api, "delete_goal", {"goal_id": created["goal_id"], "title": "Bajar a 80 kg"})
    assert done == {"deleted": "Bajar a 80 kg"}


async def test_reading_cannot_write_goals(api) -> None:
    response = await api.post(
        "/tools/create_goal",
        json={"title": "Something", "kind": "periodic", "period": "day"},
        headers=READ,
    )
    assert response.status_code == 403


async def test_list_metrics_is_empty_without_publishers(api) -> None:
    assert (await call(api, "list_metrics", {}, READ)) == {"metrics": []}
