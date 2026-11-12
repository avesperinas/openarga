from __future__ import annotations

from datetime import timedelta

from arga_widgets import validate
from goals.common import today


async def categories(api) -> dict[str, str]:
    response = await api.get("/categories")
    assert response.status_code == 200, response.text
    return {one["name"]: one["id"] for one in response.json()}


async def add(api, category: str, title: str, **extra) -> dict:
    response = await api.post("/tasks", json={"category_id": category, "title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def day(offset: int) -> str:
    return (today() + timedelta(days=offset)).isoformat()


async def test_each_person_starts_with_seven_categories_once(api) -> None:
    assert list(await categories(api)) == [
        "Trabajo",
        "Casa",
        "Personal",
        "Salud",
        "Dinero",
        "Aprender",
        "Deporte",
    ]
    for category_id in (await categories(api)).values():
        assert (await api.delete(f"/categories/{category_id}")).status_code == 204
    assert await categories(api) == {}


async def test_pending_go_by_date_and_the_undated_last(api) -> None:
    mine = await categories(api)
    await add(api, mine["Casa"], "Ordenar el trastero")
    await add(api, mine["Trabajo"], "Preparar la reunión", due_on=day(1))
    await add(api, mine["Trabajo"], "Enviar la factura", due_on=day(-3))
    await add(api, mine["Casa"], "Llamar al fontanero", due_on=day(0), due_time="23:59")

    listed = (await api.get("/tasks")).json()
    assert [(one["title"], one["status"]) for one in listed] == [
        ("Enviar la factura", "overdue"),
        ("Llamar al fontanero", "today"),
        ("Preparar la reunión", "upcoming"),
        ("Ordenar el trastero", "someday"),
    ]
    assert listed[1]["category"] == "Casa" and listed[1]["due_time"] == "23:59:00"

    counted = {
        one["name"]: (one["pending"], one["overdue"])
        for one in (await api.get("/categories")).json()
        if one["pending"]
    }
    assert counted == {"Trabajo": (2, 1), "Casa": (2, 0)}


async def test_done_and_undone(api) -> None:
    mine = await categories(api)
    task = await add(api, mine["Personal"], "Renovar la cuota", due_on=day(2))

    done = await api.post(f"/tasks/{task['id']}/done")
    assert done.status_code == 200, done.text
    assert done.json()["task"]["status"] == "done" and done.json()["next"] is None
    assert done.json()["task"]["done_by_me"] is True
    assert (await api.get("/tasks")).json() == []
    assert [one["title"] for one in (await api.get("/tasks?state=done")).json()] == [
        "Renovar la cuota"
    ]

    again = await api.post(f"/tasks/{task['id']}/done")
    assert again.status_code == 409

    undone = await api.post(f"/tasks/{task['id']}/undo")
    assert undone.json()["status"] == "upcoming"
    assert [one["id"] for one in (await api.get("/tasks")).json()] == [task["id"]]


async def test_a_repeating_task_brings_the_next_when_done(api) -> None:
    mine = await categories(api)
    first = today()
    task = await add(
        api, mine["Casa"], "Sacar la basura", due_on=first.isoformat(), rule="FREQ=WEEKLY;COUNT=2"
    )
    assert task["repeats"] == "cada semana, 2 veces"

    done = (await api.post(f"/tasks/{task['id']}/done")).json()
    following = done["next"]
    assert following["due_on"] == (first + timedelta(days=7)).isoformat()
    assert following["rule"] == task["rule"]

    last = (await api.post(f"/tasks/{following['id']}/done")).json()
    assert last["next"] is None

    refused = await api.post(f"/tasks/{task['id']}/undo")
    assert refused.status_code == 409
    await api.post(f"/tasks/{following['id']}/undo")
    back = await api.post(f"/tasks/{task['id']}/undo")
    assert back.status_code == 200
    assert [one["id"] for one in (await api.get("/tasks")).json()] == [task["id"]]


async def test_what_is_sent_as_null_is_removed(api) -> None:
    mine = await categories(api)
    task = await add(api, mine["Trabajo"], "Revisar el PR", due_on=day(0), due_time="10:00")

    moved = await api.put(
        f"/tasks/{task['id']}", json={"category_id": mine["Casa"], "due_time": None}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["category"] == "Casa" and moved.json()["due_time"] is None
    assert moved.json()["due_on"] == day(0)

    undated = await api.put(f"/tasks/{task['id']}", json={"due_on": None})
    assert undated.json()["status"] == "someday"


async def test_an_hour_or_a_repetition_needs_a_day(api) -> None:
    mine = await categories(api)
    hour = await api.post(
        "/tasks", json={"category_id": mine["Casa"], "title": "X", "due_time": "10:00"}
    )
    assert hour.status_code == 409
    rule = await api.post(
        "/tasks", json={"category_id": mine["Casa"], "title": "X", "rule": "FREQ=DAILY"}
    )
    assert rule.status_code == 409


async def test_categories_are_created_renamed_and_ordered(api) -> None:
    mine = await categories(api)
    created = await api.post("/categories", json={"name": "  Universidad ", "hue": 6})
    assert created.status_code == 201
    assert created.json()["name"] == "Universidad"
    assert (await api.post("/categories", json={"name": "trabajo"})).status_code == 409

    renamed = await api.put(f"/categories/{mine['Casa']}", json={"name": "Hogar"})
    assert renamed.json()["name"] == "Hogar"

    rest = [mine[name] for name in ("Salud", "Dinero", "Aprender", "Deporte")]
    order = [created.json()["id"], mine["Personal"], mine["Casa"], mine["Trabajo"], *rest]
    ordered = await api.post("/categories/order", json={"ids": order})
    assert [one["name"] for one in ordered.json()][:4] == [
        "Universidad",
        "Personal",
        "Hogar",
        "Trabajo",
    ]
    assert (await api.post("/categories/order", json={"ids": order[:2]})).status_code == 409


async def test_deleting_a_category_takes_its_tasks(api) -> None:
    mine = await categories(api)
    await add(api, mine["Trabajo"], "Algo del trabajo", due_on=day(1))
    await add(api, mine["Casa"], "Algo de casa")
    assert (await api.delete(f"/categories/{mine['Trabajo']}")).status_code == 204
    assert [one["title"] for one in (await api.get("/tasks")).json()] == ["Algo de casa"]


async def test_the_widget_shows_today_and_what_is_overdue(api) -> None:
    mine = await categories(api)
    nothing = (await api.get("/widgets/today")).json()
    assert nothing["state"] == "empty"
    assert nothing["body"]["detail"] == "Nada para hoy · nada para hoy ni para mañana"

    await add(api, mine["Casa"], "Mañana toca esto", due_on=day(1))
    tomorrow = (await api.get("/widgets/today")).json()
    assert tomorrow["body"]["detail"] == "Nada para hoy · mañana, 1 tarea"

    await add(api, mine["Trabajo"], "Enviar la factura", due_on=day(-2))
    await add(api, mine["Casa"], "Llamar al fontanero", due_on=day(0), due_time="23:59")
    ready = (await api.get("/widgets/today")).json()
    assert ready["state"] == "ready"
    validate("tasks", ready["body"], "ready")
    assert ready["body"]["checkable"] is True
    assert ready["body"]["count"] == 2
    invoice, plumber = ready["body"]["tasks"]
    assert invoice["title"] == "Enviar la factura"
    assert invoice["overdue"] is True
    assert invoice["due"] == day(-2)
    assert invoice["detail"] == "Trabajo"
    assert plumber["title"] == "Llamar al fontanero"
    assert plumber["due"] == f"{day(0)}T23:59:00"
    assert "overdue" not in plumber


async def test_a_task_is_ticked_from_the_card_and_the_card_says_what_is_left(api) -> None:
    mine = await categories(api)
    await add(api, mine["Casa"], "Regar", due_on=day(0))
    await add(api, mine["Casa"], "Barrer", due_on=day(0))
    card = (await api.get("/widgets/today")).json()
    water = next(t for t in card["body"]["tasks"] if t["title"] == "Regar")

    ticked = await api.post("/widgets/today/act", json={"verb": "complete", "id": water["id"]})
    assert ticked.status_code == 200, ticked.text
    assert [t["title"] for t in ticked.json()["body"]["tasks"]] == ["Barrer"]
    assert (await api.get(f"/tasks/{water['id']}")).json()["status"] == "done"

    back = await api.post("/widgets/today/act", json={"verb": "reopen", "id": water["id"]})
    assert back.status_code == 200
    assert {t["title"] for t in back.json()["body"]["tasks"]} == {"Regar", "Barrer"}


async def test_the_card_only_does_what_it_says(api) -> None:
    mine = await categories(api)
    await add(api, mine["Casa"], "Regar", due_on=day(0))
    task = (await api.get("/widgets/today")).json()["body"]["tasks"][0]
    wrong_verb = await api.post("/widgets/today/act", json={"verb": "delete", "id": task["id"]})
    assert wrong_verb.status_code == 422
    not_a_task = await api.post("/widgets/today/act", json={"verb": "complete", "id": "x"})
    assert not_a_task.status_code == 422
    missing = await api.post(
        "/widgets/today/act",
        json={"verb": "complete", "id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing.status_code == 404
    nowhere = await api.post("/widgets/nope/act", json={"verb": "complete", "id": task["id"]})
    assert nowhere.status_code == 404
    assert (await api.get("/widgets/today")).json()["body"]["count"] == 1


async def test_upcoming_and_overdue(api) -> None:
    mine = await categories(api)
    await add(api, mine["Casa"], "Vencida", due_on=day(-3))
    await add(api, mine["Casa"], "En cinco días", due_on=day(5))
    await add(api, mine["Casa"], "En un mes", due_on=day(30))
    upcoming = (await api.get("/widgets/upcoming")).json()["body"]
    assert [t["title"] for t in upcoming["tasks"]] == ["Vencida", "En cinco días"]
    overdue = (await api.get("/widgets/overdue")).json()["body"]
    assert [t["title"] for t in overdue["tasks"]] == ["Vencida"]
    for widget in ("today", "upcoming", "overdue"):
        envelope = (await api.get(f"/widgets/{widget}")).json()
        validate("tasks", envelope["body"], envelope["state"])


async def test_a_category_that_is_not_one_is_not_found(api) -> None:
    missing = await api.post("/tasks", json={"category_id": "", "title": "X"})
    assert missing.status_code == 404
