from __future__ import annotations

import pytest

from arga_widgets import BadBody, UnknownKind, envelope, validate


def test_a_field_from_another_kind_is_rejected() -> None:
    with pytest.raises(BadBody) as error:
        validate("heatmap", {"series": [1, 2, 3]})

    assert "heatmap" in str(error.value)
    assert "series" in str(error.value)


def test_a_ready_body_without_its_data_is_rejected() -> None:
    with pytest.raises(BadBody) as error:
        validate("chart", {"value": 7, "detail": "esta semana"})

    assert "series" in str(error.value)
    assert "empty" in str(error.value)


def test_the_other_states_may_carry_only_the_reason() -> None:
    assert validate("chart", {"detail": "sin datos todavía"}, state="empty") == {
        "detail": "sin datos todavía"
    }
    assert validate("upnext", {"detail": "Google Calendar no contesta"}, state="disconnected")


def test_each_kind_takes_its_own_shape() -> None:
    assert validate("kpi", {"value": 1284, "unit": "pasos", "detail": "12 hoy"})
    assert validate("kpi-delta", {"value": 62.5, "previous": 63.1, "good_when": "down"})
    assert validate("bars", {"series": [1, 2], "labels": ["L", "M"], "highlight": 1})
    assert validate("ring", {"value": 2, "target": 5, "show": "value"})
    assert validate("streak", {"current": 4, "best": 9, "days": [True, False]})
    assert validate("stats", {"stats": [{"label": "Series", "value": 18}]})
    assert validate("list", {"rows": [{"label": "Pull", "value": "52 min"}]})
    assert validate("calendar", {"marked": [1, 3, 8], "today": 17})
    assert validate("upnext", {"events": [{"at": "2026-09-18T18:00:00Z", "title": "Push"}]})
    assert validate("shortcuts", {"actions": [{"label": "Empezar", "href": "/training"}]})


def test_a_value_of_the_wrong_type_is_rejected() -> None:
    with pytest.raises(BadBody):
        validate("ring", {"value": 2, "target": 5, "show": "porcentaje"})
    with pytest.raises(BadBody):
        validate("stats", {"stats": [{"label": "Series"}]})


def test_a_kind_the_shell_cannot_paint_is_rejected() -> None:
    with pytest.raises(UnknownKind):
        validate("gauge", {"value": 1})


def test_the_envelope_carries_the_checked_body() -> None:
    sealed = envelope("kpi", "ready", {"value": 3, "detail": "hoy"})

    assert sealed["state"] == "ready"
    assert sealed["body"] == {"value": 3, "detail": "hoy"}
    assert sealed["updated_at"].endswith("+00:00")
    assert "uncertainty" not in sealed


def test_the_envelope_passes_the_doubt_through() -> None:
    sealed = envelope("kpi", "ready", {"value": 3}, {"summary": "dos comercios se parecen"})

    assert sealed["uncertainty"] == {"summary": "dos comercios se parecen"}
