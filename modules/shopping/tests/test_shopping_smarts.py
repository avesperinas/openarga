from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

import pytest

from shopping import guess, habits, names

D = date(2026, 9, 1)


def days(*offsets: int) -> list[date]:
    return [D + timedelta(days=offset) for offset in offsets]


def test_the_same_product_written_three_ways_is_one() -> None:
    assert names.key("Plátanos") == names.key("platanos ") == names.key("PLÁTANOS")
    assert names.key("  Leche   semidesnatada ") == "leche semidesnatada"


def test_a_product_is_shown_as_it_was_written_with_a_capital() -> None:
    assert names.clean("  leche   sin lactosa ") == "Leche sin lactosa"


def test_typing_finds_the_start_of_any_word() -> None:
    assert names.starts_a_word("plat", "Plátanos")
    assert names.starts_a_word("plat", "Papel de plata")
    assert not names.starts_a_word("plat", "Espátula")
    assert not names.starts_a_word("", "Plátanos")


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("Leche semidesnatada", "dairy"),
        ("Tomates", "produce"),
        ("Champiñones", "produce"),
        ("Merluza", "fish"),
        ("Pechuga de pollo", "meat"),
        ("Queso curado", "deli"),
        ("Pan de molde", "bakery"),
        ("Café molido", "breakfast"),
        ("Helado de chocolate", "frozen"),
        ("Cerveza", "drinks"),
        ("Lejía", "cleaning"),
        ("Champú", "hygiene"),
        ("Arroz", "pantry"),
    ],
)
def test_a_new_product_falls_in_its_section(name: str, category: str) -> None:
    assert guess.category(name) == category


def test_a_phrase_wins_over_its_words() -> None:
    assert guess.category("Tomate frito") == "pantry"
    assert guess.category("Papel higiénico") == "hygiene"
    assert guess.category("Arroz con leche") == "dairy"


def test_the_first_word_that_matches_decides() -> None:
    assert guess.category("Yogur de fresa") == "dairy"


def test_what_the_dictionary_does_not_know_goes_to_other() -> None:
    assert guess.category("Cosa rara") == guess.OTHER


def test_every_section_in_the_dictionary_exists() -> None:
    from shopping.shopping import CATEGORY_IDS

    used = set(guess.WORDS) | set(guess.PHRASES.values())
    assert used <= set(CATEGORY_IDS)


def test_a_word_belongs_to_one_section_only() -> None:
    counted = Counter(names.fold(word) for words in guess.WORDS.values() for word in words)
    assert [word for word, times in counted.items() if times > 1] == []
    assert all(" " not in word for words in guess.WORDS.values() for word in words)


def test_with_less_than_three_purchases_it_is_not_known_yet() -> None:
    assert habits.habit(days(0, 7)).every_days is None
    assert habits.habit([]).times == 0


def test_the_habit_is_the_median_so_a_holiday_does_not_move_it() -> None:
    found = habits.habit(days(0, 7, 14, 35, 42))

    assert found.every_days == 7
    assert found.times == 5
    assert found.last == D + timedelta(days=42)


def test_two_purchases_on_the_same_day_are_one() -> None:
    found = habits.habit(days(0, 0, 7, 14))

    assert found.times == 3
    assert found.every_days == 7


def test_it_is_due_once_its_interval_has_gone_by() -> None:
    found = habits.habit(days(0, 7, 14))

    assert not found.due(D + timedelta(days=20))
    assert found.due(D + timedelta(days=21))
    assert found.overdue(D + timedelta(days=28)) == 2.0


def test_the_habit_is_said_as_it_would_be_said() -> None:
    assert habits.every_label(7) == "cada semana"
    assert habits.every_label(14) == "cada 2 semanas"
    assert habits.every_label(3.5) == "cada 4 días"
    assert habits.every_label(1) == "cada día"
    assert habits.since_label(0) == "hoy"
    assert habits.since_label(1) == "ayer"
    assert habits.since_label(9) == "hace 9 días"
