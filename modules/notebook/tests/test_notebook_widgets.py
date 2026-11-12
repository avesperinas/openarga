from __future__ import annotations

from arga_widgets import validate
from notebook.widgets import KINDS


async def widget(api, name: str) -> dict:
    response = await api.get(f"/widgets/{name}")
    assert response.status_code == 200, response.text
    body = response.json()
    validate(KINDS[name], body["body"], body["state"])
    return body


async def test_empty_widgets_say_why(api) -> None:
    for name in KINDS:
        body = await widget(api, name)
        assert body["state"] == "empty"
        assert body["body"]["detail"]


async def test_recent_marks_what_claude_changed_and_today_shows_its_first_lines(api) -> None:
    await api.post("/notes", json={"title": "Mía"})
    await api.post(
        "/tools/create_note",
        json={"title": "De Claude"},
        headers={"x-arga-scopes": "notebook:write"},
    )
    daily = (await api.post("/daily")).json()
    await api.put(f"/notes/{daily['id']}", json={"content": "---\na: 1\n---\n# Hoy\n\n- Algo\n"})

    recent = await widget(api, "recent")
    today = await widget(api, "today")

    values = {row["label"]: row["value"] for row in recent["body"]["rows"]}
    assert values["De Claude"].startswith("Claude · ")
    assert not values["Mía"].startswith("Claude")
    assert [row["label"] for row in today["body"]["rows"]] == ["Hoy", "Algo"]
