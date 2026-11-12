import pytest

from arga_widgets import Act, BadPanel, panel
from arga_widgets.panel import blocks_of


def tab(blocks, **extra):
    return {"id": "resumen", "label": "Resumen", "blocks": blocks, **extra}


def test_a_panel_with_every_block_seals_and_says_when():
    found = panel(
        "money",
        order=10,
        headlines=[
            {
                "text": "Llegas a fin de mes con unos 420 €",
                "emphasis": "unos 420 €",
                "tone": "positive",
                "status": "Vas bien",
                "priority": 60,
            }
        ],
        tabs=[
            tab(
                [
                    {
                        "type": "figure",
                        "label": "Patrimonio",
                        "value": "48.320 €",
                        "delta": "+23 %",
                        "tone": "positive",
                    },
                    {
                        "type": "trend",
                        "points": [{"label": "oct", "value": 1}, {"label": "nov", "value": 2}],
                        "unit": "money",
                    },
                    {
                        "type": "split",
                        "parts": [{"label": "Gastas", "value": "1.410 €", "share": 1410, "hue": 4}],
                    },
                    {
                        "type": "tiles",
                        "items": [{"label": "Colchón", "value": "1,5 meses", "series": [1, 2]}],
                    },
                    {
                        "type": "rings",
                        "items": [{"label": "Sueño", "value": "82", "share": 0.82, "hue": 1}],
                    },
                    {
                        "type": "timeline",
                        "items": [
                            {
                                "start": "2026-11-06T18:00:00+01:00",
                                "end": "2026-11-06T19:30:00+01:00",
                                "title": "Escalada",
                            }
                        ],
                    },
                    {
                        "type": "tasks",
                        "widget": "today",
                        "items": [{"id": "t1", "title": "Pagar la comunidad"}],
                        "add": "Añadir una tarea",
                    },
                    {
                        "type": "list",
                        "rows": [{"label": "Ocio", "value": "+98 €", "tone": "warning"}],
                    },
                    {
                        "type": "alert",
                        "text": "3 movimientos por etiquetar",
                        "href": "/money/movimientos",
                    },
                    {
                        "type": "bars",
                        "labels": ["L", "M"],
                        "values": [1, 2],
                        "highlight": 1,
                        "goal": 2,
                    },
                    {"type": "treemap", "items": [{"label": "Casa", "value": 620, "hue": 1}]},
                    {
                        "type": "feature",
                        "title": "Pierna, hoy",
                        "body": ["legs"],
                        "action": "Empezar",
                        "href": "/training/",
                    },
                ],
                actions=[{"label": "Abrir Money", "href": "/money/", "primary": True}],
            )
        ],
        questions=[{"text": "¿Llego a fin de mes?", "words": ["fin de mes"], "tab": "resumen"}],
    )
    assert found["area"] == "money"
    assert "updated_at" in found
    assert [block["type"] for block in found["tabs"][0]["blocks"]][:3] == [
        "figure",
        "trend",
        "split",
    ]


def test_a_block_outside_the_list_or_with_a_field_too_many_breaks_in_the_app_tests():
    with pytest.raises(BadPanel):
        panel("money", tabs=[tab([{"type": "pie", "values": [1]}])])
    with pytest.raises(BadPanel):
        panel("money", tabs=[tab([{"type": "figure", "label": "x", "value": "1", "color": "red"}])])


def test_an_area_that_does_not_exist_a_link_off_site_or_a_question_to_nowhere_is_refused():
    with pytest.raises(BadPanel):
        panel("garden", tabs=[tab([])])
    with pytest.raises(BadPanel):
        panel("money", tabs=[tab([{"type": "alert", "text": "x", "href": "https://example.com"}])])
    with pytest.raises(BadPanel):
        panel("money", tabs=[tab([])], questions=[{"text": "¿?", "words": ["x"], "tab": "otra"}])


def test_adding_from_the_panel_is_a_verb():
    assert Act(verb="add", id="Leche").verb == "add"


def test_the_tasks_of_a_widget_become_ticks_with_a_readable_date():
    envelope = {
        "state": "ready",
        "body": {
            "tasks": [
                {"id": "a", "title": "Renovar el DNI", "due": "2026-11-04", "overdue": True},
                {"id": "b", "title": "Llamar", "detail": "a las 10:00"},
                {"id": "c", "title": "Sin fecha"},
            ],
            "checkable": True,
        },
    }
    (block,) = blocks_of("tasks", envelope, label="Hoy", widget="today")
    assert [item.get("due") for item in block["items"]] == ["4 nov", "a las 10:00", None]
    assert block["items"][0]["overdue"] is True
    panel("day", tabs=[{"id": "t", "label": "T", "blocks": [block]}])


def test_an_agenda_keeps_its_first_day_apart_from_what_comes_later():
    envelope = {
        "state": "ready",
        "body": {
            "entries": [
                {
                    "start": "2026-11-06T09:00:00+01:00",
                    "end": "2026-11-06T10:00:00+01:00",
                    "title": "Daily",
                },
                {"start": "2026-11-07T08:00:00+01:00", "title": "Dentista"},
            ]
        },
    }
    timeline, today, later = blocks_of("agenda", envelope, label="Hoy")
    assert [item["title"] for item in timeline["items"]] == ["Daily"]
    assert today["rows"] == [{"label": "Daily", "value": "09:00"}]
    assert later["rows"] == [{"label": "Dentista", "value": "7 nov · 08:00"}]


def test_an_agenda_with_nothing_today_does_not_call_tomorrow_today():
    from datetime import date

    envelope = {
        "state": "ready",
        "body": {
            "entries": [
                {"start": "2026-11-12T18:30:00+01:00", "title": "Clase"},
                {"start": "2026-11-12T20:30:00+01:00", "title": "Cena"},
            ]
        },
    }
    (later,) = blocks_of("agenda", envelope, label="Hoy", today=date(2026, 11, 11))
    assert later["label"] == "Después"
    assert [row["label"] for row in later["rows"]] == ["Clase", "Cena"]
    timeline, today = blocks_of("agenda", envelope, label="Hoy", today=date(2026, 11, 12))
    assert len(timeline["items"]) == 2
    assert today["rows"][0] == {"label": "Clase", "value": "18:30"}


async def test_a_widget_that_breaks_does_not_take_the_ones_after_it():
    from contextlib import asynccontextmanager

    from arga_widgets.panel import gather

    class Connection:
        def __init__(self) -> None:
            self.savepoints = 0
            self.rolled_back = 0

        @asynccontextmanager
        async def begin_nested(self):
            self.savepoints += 1
            try:
                yield
            except Exception:
                self.rolled_back += 1
                raise

    async def broken(connection):
        raise RuntimeError("relation does not exist")

    async def fine(connection):
        return {"state": "ready", "body": {"value": 1}}

    connection = Connection()
    found = await gather(connection, {"a": broken, "b": fine}, ["a", "b", "missing"])
    assert list(found) == ["b"]
    assert (connection.savepoints, connection.rolled_back) == (2, 1)
