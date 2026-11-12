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
            "title": "Sacar la basura",
            "category": "casa",
            "due_on": first.isoformat(),
            "repeat": {"freq": "weekly", "by_day": [{"weekday": "TU"}]},
        },
    )
    assert created["category"] == "Casa"
    assert created["repeats"] == "cada semana, el martes"

    done = await call(api, "complete_task", {"task_id": created["task_id"]})
    assert done["done"]["status"] == "done"
    assert done["next"]["due_on"] == (first + timedelta(days=7)).isoformat()

    listed = (await api.get("/tasks")).json()
    assert [(one["title"], one["due_on"]) for one in listed] == [
        ("Sacar la basura", (first + timedelta(days=7)).isoformat())
    ]


async def test_reading_with_the_reader_role(api) -> None:
    await call(
        api,
        "add_task",
        {
            "title": "Enviar la factura",
            "category": "Trabajo",
            "due_on": (today() - timedelta(days=1)).isoformat(),
        },
    )
    await call(api, "add_task", {"title": "Leer sobre índices", "category": "Personal"})

    due = await call(api, "find_tasks", {"due_until": today().isoformat()}, READ)
    assert [(one["title"], one["status"]) for one in due["tasks"]] == [
        ("Enviar la factura", "overdue")
    ]

    found = await call(api, "find_tasks", {"query": "indices"}, READ)
    assert [one["title"] for one in found["tasks"]] == ["Leer sobre índices"]

    counted = await call(api, "get_categories", {}, READ)
    assert {one["name"]: one["overdue"] for one in counted["categories"]} == {
        "Trabajo": 1,
        "Casa": 0,
        "Personal": 0,
    }


async def test_the_reader_role_cannot_add(api) -> None:
    await call(api, "get_categories", {}, WRITE)
    refused = await api.post(
        "/tools/add_task", json={"title": "X", "category": "Casa"}, headers=READ
    )
    assert refused.status_code == 403


async def test_an_unknown_category_says_which_there_are(api) -> None:
    answer = await call(api, "add_task", {"title": "X", "category": "Recados"})
    assert answer["error"] == "no hay una categoría 'Recados'. Las que hay: Trabajo, Casa, Personal"
    created = await call(api, "add_category", {"name": "Recados"})
    assert created == {"name": "Recados", "hue": 3}
    added = await call(api, "add_task", {"title": "Recoger el paquete", "category": "recados"})
    assert added["category"] == "Recados"


async def test_a_tool_that_fails_leaves_nothing_behind(api, schema) -> None:
    from sqlalchemy import text

    answer = await call(api, "add_task", {"title": "X", "category": "Recados"})
    assert "Recados" in answer["error"]
    async with schema.begin() as connection:
        seeded = await connection.scalar(text("select count(*) from goals.goals_category"))
    assert seeded == 0


async def test_update_moves_and_clears(api) -> None:
    created = await call(
        api,
        "add_task",
        {
            "title": "Revisar el PR",
            "category": "Trabajo",
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
            "title": "Leer 20 minutos",
            "kind": "periodic",
            "period": "day",
            "days_per_week": 5,
            "category": "aprender",
        },
    )
    assert created["category"] == "Aprender" and created["today_met"] is False

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

    wrong = await call(api, "delete_goal", {"goal_id": created["goal_id"], "title": "Bajar"})
    assert "no coincide" in wrong["error"]
    done = await call(api, "delete_goal", {"goal_id": created["goal_id"], "title": "Bajar a 80 kg"})
    assert done == {"deleted": "Bajar a 80 kg"}


async def test_reading_cannot_write_goals(api) -> None:
    response = await api.post(
        "/tools/create_goal",
        json={"title": "Algo", "kind": "periodic", "period": "day"},
        headers=READ,
    )
    assert response.status_code == 403


async def test_list_metrics_is_empty_without_publishers(api) -> None:
    assert (await call(api, "list_metrics", {}, READ)) == {"metrics": []}
