from __future__ import annotations

from recipes.gantt import Step, overlaps, schedule


def test_sin_pasos_no_hay_diagrama() -> None:
    plan = schedule([])

    assert plan.steps == ()
    assert plan.total_minutes == 0
    assert plan.lanes == ()


def test_un_paso_empieza_en_el_minuto_cero() -> None:
    plan = schedule([Step(position=1, action="chop", text="Picar el puerro", minutes=10)])

    assert plan.steps[0].start == 0
    assert plan.steps[0].end == 10
    assert plan.total_minutes == 10
    assert plan.active_minutes == 10


def test_lo_que_depende_de_otro_espera_a_que_acabe() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Picar", minutes=10),
            Step(position=2, action="saute", text="Pochar", minutes=15, after=(1,)),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 10), (10, 25)]


def test_dos_pasos_que_te_tienen_delante_no_se_solapan() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Picar el puerro", minutes=10),
            Step(position=2, action="peel", text="Pelar la patata", minutes=8),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 10), (10, 18)]
    assert plan.total_minutes == 18
    assert plan.active_minutes == 18


def test_un_paso_desatendido_te_deja_seguir() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="bake",
                text="Al horno",
                minutes=40,
                attended=False,
                equipment="oven",
            ),
            Step(
                position=2, action="chop", text="Picar la ensalada", minutes=10, equipment="board"
            ),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 40), (0, 10)]
    assert plan.total_minutes == 40
    assert plan.active_minutes == 10


def test_lo_que_sale_del_horno_espera_al_horno() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="bake",
                text="Al horno",
                minutes=40,
                attended=False,
                equipment="oven",
            ),
            Step(position=2, action="chop", text="Picar", minutes=10, equipment="board"),
            Step(position=3, action="serve", text="Emplatar", minutes=5, after=(1, 2)),
        ]
    )

    emplatar = plan.steps[2]
    assert emplatar.start == 40
    assert plan.total_minutes == 45
    assert plan.active_minutes == 15


def test_el_cocinero_ocupado_retrasa_lo_siguiente_aunque_no_dependa_de_nada() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="simmer",
                text="Cocer",
                minutes=30,
                attended=False,
                equipment="hob",
            ),
            Step(position=2, action="chop", text="Picar", minutes=10),
            Step(position=3, action="mix", text="Mezclar", minutes=5),
        ]
    )

    assert [(one.start, one.end) for one in plan.steps] == [(0, 30), (0, 10), (10, 15)]
    assert plan.total_minutes == 30


def test_los_carriles_son_los_que_se_usan_y_en_su_orden() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Picar", minutes=5, equipment="board"),
            Step(
                position=2,
                action="bake",
                text="Hornear",
                minutes=20,
                attended=False,
                equipment="oven",
            ),
            Step(position=3, action="rest", text="Reposar", minutes=10, attended=False),
        ]
    )

    assert plan.lanes == ("oven", "board", "none")


def test_dos_cosas_en_el_mismo_fuego_a_la_vez_se_dicen() -> None:
    plan = schedule(
        [
            Step(
                position=1,
                action="simmer",
                text="Caldo",
                minutes=40,
                attended=False,
                equipment="hob",
            ),
            Step(position=2, action="fry", text="Sofrito", minutes=15, equipment="hob"),
        ]
    )

    assert [clash.equipment for clash in overlaps(plan)] == ["hob"]
    assert overlaps(plan)[0].positions == [1, 2]


def test_lo_que_no_ocupa_nada_nunca_choca() -> None:
    plan = schedule(
        [
            Step(position=1, action="rest", text="Reposar la masa", minutes=60, attended=False),
            Step(position=2, action="marinate", text="Marinar", minutes=30, attended=False),
        ]
    )

    assert overlaps(plan) == []


def test_una_receta_entera_da_sus_dos_numeros() -> None:
    plan = schedule(
        [
            Step(position=1, action="chop", text="Picar el puerro", minutes=5, equipment="board"),
            Step(
                position=2, action="peel", text="Cascar las patatas", minutes=5, equipment="board"
            ),
            Step(
                position=3,
                action="saute",
                text="Pochar el puerro",
                minutes=10,
                equipment="hob",
                after=(1,),
            ),
            Step(
                position=4,
                action="simmer",
                text="Cocer a fuego lento",
                minutes=30,
                attended=False,
                equipment="hob",
                after=(2, 3),
            ),
        ]
    )

    assert plan.total_minutes == 50
    assert plan.active_minutes == 20
    assert plan.steps[-1].start == 20
