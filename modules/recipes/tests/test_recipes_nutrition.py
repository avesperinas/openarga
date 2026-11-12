from __future__ import annotations

import pytest

from recipes.nutrition import (
    Convertible,
    Item,
    Per100g,
    per_serving,
    to_grams,
    totals,
    uncertainty,
)

LEEK = Per100g(kcal=61, protein=1.5, fat=0.3, carbs=14.15, fiber=1.8, salt=0.05)
OIL = Per100g(kcal=884, protein=0, fat=100, carbs=0)


def test_gramos_son_gramos() -> None:
    assert to_grams(300, "g", None) == 300


def test_un_liquido_necesita_su_densidad() -> None:
    aceite = Convertible(density_g_ml=0.92)

    assert to_grams(100, "ml", aceite) == pytest.approx(92)
    assert to_grams(2, "tbsp", aceite) == pytest.approx(27.6)
    assert to_grams(1, "tsp", aceite) == pytest.approx(4.6)


def test_sin_densidad_un_liquido_no_se_estima() -> None:
    assert to_grams(100, "ml", Convertible()) is None


def test_una_unidad_necesita_cuanto_pesa_una() -> None:
    huevo = Convertible(grams_per_unit=60)

    assert to_grams(2, "unit", huevo) == 120
    assert to_grams(0.5, "unit", Convertible()) is None


def test_una_pizca_pesa_lo_mismo_para_todo() -> None:
    assert to_grams(1, "pinch", None) == 0.5


def test_la_suma_sale_de_los_gramos_de_cada_uno() -> None:
    total = totals(
        [
            Item(quantity=300, unit="g", macros=LEEK, measures=Convertible(), label="Puerro"),
            Item(
                quantity=10,
                unit="ml",
                macros=OIL,
                measures=Convertible(density_g_ml=0.92),
                label="Aceite",
            ),
        ]
    )

    assert total.kcal == pytest.approx(264.3, abs=0.2)
    assert total.grams == pytest.approx(309.2, abs=0.1)
    assert total.counted == 2
    assert total.complete


def test_lo_que_no_se_puede_convertir_se_deja_fuera_y_se_dice() -> None:
    total = totals(
        [
            Item(quantity=300, unit="g", macros=LEEK, measures=Convertible(), label="Puerro"),
            Item(quantity=1, unit="unit", macros=None, measures=None, label="sofrito de casa"),
            Item(quantity=0.5, unit="unit", macros=LEEK, measures=Convertible(), label="Cebolla"),
        ]
    )

    assert total.counted == 1
    assert total.total == 3
    assert total.missing == ("sofrito de casa", "Cebolla")
    assert not total.complete
    assert uncertainty(total) == "faltan 2 de 3 ingredientes (sofrito de casa, Cebolla)"


def test_cuando_no_falta_nada_no_hay_nada_que_decir() -> None:
    total = totals([Item(quantity=100, unit="g", macros=LEEK, measures=Convertible(), label="P")])

    assert uncertainty(total) is None


def test_una_sola_ausencia_se_dice_en_singular() -> None:
    total = totals([Item(quantity=1, unit="unit", macros=None, label="sofrito")])

    assert uncertainty(total) == "falta 1 de 1 ingredientes (sofrito)"


def test_la_fibra_que_nadie_declara_no_es_cero() -> None:
    total = totals([Item(quantity=10, unit="g", macros=OIL, measures=Convertible(), label="A")])

    assert total.fiber is None
    assert total.salt is None


def test_escalar_multiplica_las_cantidades() -> None:
    uno = Item(quantity=200, unit="g", macros=LEEK, measures=Convertible(), label="Puerro")

    assert totals([uno], scale=1.5).grams == 300
    assert totals([uno], scale=1.5).kcal == pytest.approx(totals([uno]).kcal * 1.5, abs=0.2)


def test_por_racion_es_lo_que_de_verdad_se_mira() -> None:
    total = totals([Item(quantity=400, unit="g", macros=LEEK, measures=Convertible(), label="P")])

    each = per_serving(total, 4)

    assert each.kcal == pytest.approx(total.kcal / 4, abs=0.1)
    assert each.grams == pytest.approx(100, abs=0.1)
    assert each.missing == total.missing


def test_una_receta_para_cero_personas_no_existe() -> None:
    with pytest.raises(ValueError, match="al menos una"):
        per_serving(totals([]), 0)
