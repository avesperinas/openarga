from __future__ import annotations

from test_library_library import add
from test_library_stats import read

from arga_widgets import validate
from library.library import today
from library.widgets import KINDS


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


async def test_with_books_they_are_ready(api) -> None:
    year = today().year
    await add(api, "En curso", status="reading")
    await read(api, "Uno", f"{year}-01-02", f"{year}-01-20", 321)
    await api.put(f"/goals/{year}", json={"books": 12})

    reading = await widget(api, "reading")
    goal = await widget(api, "goal")
    pages = await widget(api, "pages")

    assert reading["body"]["rows"][0]["label"] == "En curso"
    assert (goal["body"]["value"], goal["body"]["target"]) == (1, 12)
    assert 0 < goal["body"]["expected"] <= 12
    assert pages["body"]["value"] == 321
    assert len(pages["body"]["series"]) == today().month
