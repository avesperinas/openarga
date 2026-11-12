import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from arga_recurrence import (
    Day,
    Rule,
    describe,
    expand,
    next_occurrence,
    parse,
    split,
    split_exceptions,
    to_rrule,
)

MADRID = ZoneInfo("Europe/Madrid")
PHRASES = json.loads((Path(__file__).parents[1] / "phrases.json").read_text())


def madrid(*args: int) -> datetime:
    return datetime(*args, tzinfo=MADRID)


def starts(occurrences):
    return [o.start for o in occurrences]


@pytest.mark.parametrize("case", PHRASES, ids=[c["rrule"] for c in PHRASES])
def test_la_frase_de_cada_caso(case):
    assert describe(parse(case["rrule"])) == case["phrase"]


@pytest.mark.parametrize("case", PHRASES, ids=[c["rrule"] for c in PHRASES])
def test_el_texto_va_y_vuelve(case):
    rule = parse(case["rrule"])
    assert parse(to_rrule(rule)) == rule


def test_el_texto_sale_siempre_en_el_mismo_orden():
    assert to_rrule(parse("BYDAY=TH,TU;FREQ=WEEKLY;INTERVAL=1")) == "FREQ=WEEKLY;BYDAY=TU,TH"
    assert to_rrule(parse("RRULE:FREQ=MONTHLY;BYMONTHDAY=-1,15,1")) == (
        "FREQ=MONTHLY;BYMONTHDAY=1,15,-1"
    )


def test_la_regla_llega_como_objeto():
    rule = Rule.model_validate(
        {"freq": "monthly", "by_day": [{"weekday": "FR", "pos": -1}], "count": 12}
    )
    assert to_rrule(rule) == "FREQ=MONTHLY;BYDAY=-1FR;COUNT=12"


@pytest.mark.parametrize(
    "text",
    [
        "FREQ=MONTHLY;BYSETPOS=-1;BYDAY=MO,TU,WE,TH,FR",
        "FREQ=DAILY;BYHOUR=9",
        "FREQ=HOURLY",
        "FREQ=WEEKLY;COUNT=3;UNTIL=20270101",
        "FREQ=WEEKLY;UNTIL=20270101T000000Z",
        "FREQ=WEEKLY;BYDAY=2TU",
        "FREQ=DAILY;BYDAY=MO",
        "FREQ=MONTHLY;BYMONTH=3",
        "FREQ=MONTHLY;BYMONTHDAY=32",
        "FREQ=MONTHLY;BYDAY=6MO",
        "FREQ=MONTHLY;BYDAY=1MO,TU",
        "FREQ=MONTHLY;BYDAY=MO;BYMONTHDAY=1",
        "FREQ=YEARLY;BYDAY=-1SU",
        "FREQ=WEEKLY;WKST=SU",
        "FREQ=WEEKLY;INTERVAL=0",
    ],
)
def test_lo_que_no_cabe_en_el_subconjunto_revienta(text):
    with pytest.raises((ValueError, ValidationError)):
        parse(text)


def test_una_serie_a_las_diez_sigue_a_las_diez_tras_el_cambio_de_marzo():
    rule = parse("FREQ=WEEKLY;BYDAY=TU")
    found = expand(
        rule, datetime(2027, 3, 16, 10), "Europe/Madrid", madrid(2027, 3, 15), madrid(2027, 4, 5)
    )
    assert [(o.start.hour, o.start.utcoffset()) for o in found] == [
        (10, timedelta(hours=1)),
        (10, timedelta(hours=1)),
        (10, timedelta(hours=2)),
    ]


def test_y_tras_el_de_octubre():
    rule = parse("FREQ=DAILY")
    found = expand(
        rule, datetime(2027, 10, 30, 10), "Europe/Madrid", madrid(2027, 10, 30), madrid(2027, 11, 1)
    )
    assert [o.start.hour for o in found] == [10, 10]
    assert found[1].start.astimezone(UTC) - found[0].start.astimezone(UTC) == timedelta(hours=25)


def test_una_hora_que_marzo_se_salta_cae_en_la_siguiente_que_existe():
    rule = parse("FREQ=DAILY;COUNT=3")
    found = expand(
        rule, datetime(2027, 3, 27, 2, 30), "Europe/Madrid", madrid(2027, 3, 1), madrid(2027, 4, 1)
    )
    assert [(o.start.day, o.start.hour, o.start.minute) for o in found] == [
        (27, 2, 30),
        (28, 3, 30),
        (29, 2, 30),
    ]
    assert found[1].original == datetime(2027, 3, 28, 2, 30)


def test_la_ventana_puede_venir_en_otra_zona():
    rule = parse("FREQ=DAILY")
    found = expand(
        rule,
        datetime(2027, 7, 1, 23, 30),
        "Europe/Madrid",
        datetime(2027, 7, 1, tzinfo=UTC),
        datetime(2027, 7, 2, tzinfo=UTC),
    )
    assert starts(found) == [madrid(2027, 7, 1, 23, 30)]


def test_la_ventana_es_semiabierta():
    rule = parse("FREQ=DAILY")
    found = expand(
        rule, datetime(2027, 1, 1, 9), "Europe/Madrid", madrid(2027, 1, 2, 9), madrid(2027, 1, 4, 9)
    )
    assert [o.start.day for o in found] == [2, 3]


def test_el_dia_31_se_salta_los_meses_que_no_lo_tienen():
    rule = parse("FREQ=MONTHLY;BYMONTHDAY=31")
    found = expand(rule, date(2027, 1, 31), "Europe/Madrid", date(2027, 1, 1), date(2028, 1, 1))
    assert [o.start.month for o in found] == [1, 3, 5, 7, 8, 10, 12]


def test_el_ultimo_dia_si_cae_en_todos_los_meses():
    rule = parse("FREQ=MONTHLY;BYMONTHDAY=-1")
    found = expand(rule, date(2028, 1, 31), "Europe/Madrid", date(2028, 1, 1), date(2028, 4, 1))
    assert starts(found) == [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)]


def test_el_29_de_febrero_solo_en_bisiesto():
    rule = parse("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29")
    found = expand(rule, date(2028, 2, 29), "Europe/Madrid", date(2028, 1, 1), date(2037, 1, 1))
    assert [o.start.year for o in found] == [2028, 2032, 2036]


def test_el_ultimo_viernes():
    rule = parse("FREQ=MONTHLY;BYDAY=-1FR")
    found = expand(rule, date(2027, 1, 29), "Europe/Madrid", date(2027, 1, 1), date(2027, 5, 1))
    assert starts(found) == [
        date(2027, 1, 29),
        date(2027, 2, 26),
        date(2027, 3, 26),
        date(2027, 4, 30),
    ]


def test_el_ultimo_domingo_de_octubre():
    rule = parse("FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU")
    found = expand(rule, date(2026, 10, 25), "Europe/Madrid", date(2026, 1, 1), date(2029, 1, 1))
    assert starts(found) == [date(2026, 10, 25), date(2027, 10, 31), date(2028, 10, 29)]


def test_cada_dos_semanas_cuenta_desde_la_semana_del_inicio():
    rule = parse("FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH")
    found = expand(rule, date(2027, 1, 7), "Europe/Madrid", date(2027, 1, 1), date(2027, 2, 1))
    assert starts(found) == [date(2027, 1, 7), date(2027, 1, 19), date(2027, 1, 21)]


def test_lo_que_no_dice_la_regla_lo_toma_del_inicio():
    found = expand(
        parse("FREQ=MONTHLY"),
        date(2027, 1, 12),
        "Europe/Madrid",
        date(2027, 1, 1),
        date(2027, 4, 1),
    )
    assert [o.start.day for o in found] == [12, 12, 12]


def test_hasta_una_fecha_incluye_ese_dia():
    rule = parse("FREQ=DAILY;UNTIL=20270105")
    found = expand(
        rule, datetime(2027, 1, 1, 20), "Europe/Madrid", madrid(2027, 1, 1), madrid(2027, 2, 1)
    )
    assert [o.start.day for o in found] == [1, 2, 3, 4, 5]


def test_una_cancelada_no_sale_y_una_movida_sale_donde_cae_ahora():
    rule = parse("FREQ=WEEKLY;BYDAY=MO")
    found = expand(
        rule,
        datetime(2027, 1, 4, 10),
        "Europe/Madrid",
        madrid(2027, 1, 1),
        madrid(2027, 2, 1),
        cancelled=[datetime(2027, 1, 11, 10)],
        moved={datetime(2027, 1, 18, 10): datetime(2027, 1, 19, 18)},
    )
    assert starts(found) == [
        madrid(2027, 1, 4, 10),
        madrid(2027, 1, 19, 18),
        madrid(2027, 1, 25, 10),
    ]
    assert found[1].moved and found[1].original == datetime(2027, 1, 18, 10)


def test_una_movida_desde_fuera_de_la_ventana_entra():
    rule = parse("FREQ=WEEKLY;BYDAY=MO")
    found = expand(
        rule,
        datetime(2027, 1, 4, 10),
        "Europe/Madrid",
        madrid(2027, 2, 1),
        madrid(2027, 2, 8),
        moved={datetime(2027, 1, 25, 10): datetime(2027, 2, 3, 10)},
    )
    assert starts(found) == [madrid(2027, 2, 1, 10), madrid(2027, 2, 3, 10)]


def test_una_excepcion_que_no_es_de_la_serie_se_ignora():
    rule = parse("FREQ=WEEKLY;BYDAY=MO")
    found = expand(
        rule,
        datetime(2027, 1, 4, 10),
        "Europe/Madrid",
        madrid(2027, 1, 4),
        madrid(2027, 1, 11),
        moved={datetime(2027, 1, 5, 10): datetime(2027, 1, 6, 10)},
    )
    assert starts(found) == [madrid(2027, 1, 4, 10)]


def test_cortar_una_serie_sin_fin():
    rule = parse("FREQ=WEEKLY;BYDAY=TU")
    head, tail = split(rule, datetime(2027, 1, 5, 10), datetime(2027, 2, 2, 10))
    assert head is not None
    assert to_rrule(head) == "FREQ=WEEKLY;BYDAY=TU;UNTIL=20270126T100000"
    assert tail == rule
    before = expand(
        head, datetime(2027, 1, 5, 10), "Europe/Madrid", madrid(2027, 1, 1), madrid(2027, 3, 1)
    )
    after = expand(
        tail, datetime(2027, 2, 2, 10), "Europe/Madrid", madrid(2027, 1, 1), madrid(2027, 3, 1)
    )
    assert [o.start.day for o in before] == [5, 12, 19, 26]
    assert [o.start.day for o in after] == [2, 9, 16, 23]


def test_cortar_reparte_las_veces():
    rule = parse("FREQ=DAILY;COUNT=10")
    head, tail = split(rule, date(2027, 1, 1), date(2027, 1, 4))
    assert head is not None and head.count == 3
    assert tail.count == 7


def test_cortar_en_la_primera_no_deja_nada_antes():
    rule = parse("FREQ=DAILY")
    head, tail = split(rule, date(2027, 1, 1), date(2027, 1, 1))
    assert head is None and tail == rule


def test_cortar_de_todo_el_dia_acaba_el_dia_anterior():
    head, _ = split(parse("FREQ=DAILY"), date(2027, 1, 1), date(2027, 1, 10))
    assert head is not None and head.until == date(2027, 1, 9)


def test_cortar_acaba_en_la_ultima_ocurrencia_de_antes():
    head, _ = split(
        parse("FREQ=WEEKLY;BYDAY=MO"), datetime(2026, 10, 5, 7, 30), datetime(2026, 10, 19, 7, 30)
    )
    assert head is not None and head.until == datetime(2026, 10, 12, 7, 30)
    assert describe(head).endswith("hasta el 12 de octubre de 2026")


def test_no_se_corta_por_donde_no_hay_ocurrencia():
    with pytest.raises(ValueError):
        split(parse("FREQ=WEEKLY;BYDAY=TU"), date(2027, 1, 5), date(2027, 1, 6))


def test_cortar_con_ocurrencias_ya_cambiadas():
    rule = parse("FREQ=WEEKLY;BYDAY=MO")
    start = datetime(2027, 1, 4, 10)
    at = datetime(2027, 1, 25, 10)
    moved = {
        datetime(2027, 1, 11, 10): datetime(2027, 1, 12, 10),
        datetime(2027, 2, 1, 10): datetime(2027, 2, 2, 10),
    }
    cancelled = {datetime(2027, 1, 18, 10): None, datetime(2027, 2, 8, 10): None}
    head, tail = split(rule, start, at)
    old_moved, new_moved = split_exceptions(moved, at)
    old_cancelled, new_cancelled = split_exceptions(cancelled, at)
    assert head is not None

    window = (madrid(2027, 1, 1), madrid(2027, 3, 1))
    old = expand(head, start, "Europe/Madrid", *window, cancelled=old_cancelled, moved=old_moved)
    new = expand(tail, at, "Europe/Madrid", *window, cancelled=new_cancelled, moved=new_moved)
    assert [(o.start.month, o.start.day) for o in old] == [(1, 4), (1, 12)]
    assert [(o.start.month, o.start.day) for o in new] == [(1, 25), (2, 2), (2, 15), (2, 22)]


def test_la_siguiente_desde_hoy():
    rule = parse("FREQ=YEARLY;BYMONTH=4;BYMONTHDAY=12")
    assert next_occurrence(rule, date(2025, 4, 12), date(2026, 9, 27)) == date(2027, 4, 12)
    assert next_occurrence(rule, date(2025, 4, 12), date(2027, 4, 12)) == date(2027, 4, 12)


def test_la_siguiente_de_una_serie_acabada():
    rule = parse("FREQ=DAILY;COUNT=2")
    assert next_occurrence(rule, date(2027, 1, 1), date(2027, 1, 3)) is None


def test_la_hora_de_pared_no_lleva_zona():
    with pytest.raises(ValueError):
        expand(
            parse("FREQ=DAILY"),
            madrid(2027, 1, 1, 10),
            "Europe/Madrid",
            madrid(2027, 1, 1),
            madrid(2027, 1, 2),
        )


def test_un_dia_con_posicion():
    assert Day(weekday="TU", pos=2) == parse("FREQ=MONTHLY;BYDAY=2TU").by_day[0]
