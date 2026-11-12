import corpus
import pytest

from kernel.identity import AUTO_MERGE_CONFIDENCE as AUTO_MERGE
from kernel.identity import compare, normalise

SEED_SPELLINGS = ["ALBA MARKET 221", "SUPERM. ALBA 0221", "ALBA MARKET SA"]


@pytest.mark.parametrize(
    ("alias", "text", "numeric", "distinctive"),
    [
        ("MERCADITO SA", "mercadito", (), {"mercadito"}),
        ("COMPRA EN PANADERÍA LOS TILOS", "panaderia los tilos", (), {"tilos"}),
        ("ALBA MARKET 0221", "alba market", ("221",), {"alba"}),
        ("E.S. KM-42 NORTE", "km norte", ("42",), {"norte"}),
        ("Casa Pérez, S.L.", "casa perez", (), {"casa", "perez"}),
    ],
)
def test_normalisation_keeps_only_what_identifies(
    alias: str, text: str, numeric: tuple, distinctive: set
) -> None:
    result = normalise(alias)

    assert result.text == text
    assert result.numeric == numeric
    assert set(result.distinctive) == distinctive


def test_a_store_number_loses_its_leading_zeros() -> None:
    assert normalise("ALBA 0221").numeric == normalise("ALBA 221").numeric


def test_a_glued_token_is_split_into_letters_and_digits() -> None:
    assert normalise("ES KM42").alpha == ("es", "km")
    assert normalise("Casa Pérez, S.L.").text == "casa perez"
    assert normalise("ES KM42").numeric == ("42",)


@pytest.mark.parametrize(
    ("left", "right", "rule"),
    [
        ("ALBA MARKET", "COMPRA EN ALBA MARKET SA", "identical"),
        ("ALBA MARKET 221", "ALBA MARKET 305", "same_name_other_store"),
        ("PANADERIA LOS TILOS VALENCIA", "PANADERIA LOS TILOS VALEN", "truncated"),
        ("ALBA MARKET 221", "SUPERM. ALBA 0221", "same_store_number"),
    ],
)
def test_the_rules_fire_where_they_should(left: str, right: str, rule: str) -> None:
    verdict = compare(left, right)

    assert verdict is not None, f"{left!r} y {right!r} deberían casar"
    assert verdict.rule == rule


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("FARMACIA VALDUERNA", "FARMACIA VALDEMORO"),
        ("CLINICA DENTAL SAUCE", "BAR EL SAUCE"),
        ("LIBRERIA ORIOL", "TALLERES ORIOL"),
        ("ALBA MARKET 221", "NORTECLIMA INSTALACIONES 221"),
        ("SUPERMERCADO", "SUPERMERCADO"),
    ],
)
def test_a_shared_category_word_never_merges(left: str, right: str) -> None:
    verdict = compare(left, right)

    assert verdict is None or verdict.confidence < AUTO_MERGE, verdict


def test_the_three_spellings_of_the_seed_resolve_without_a_model() -> None:
    verdicts = {
        (left, right): compare(left, right)
        for index, left in enumerate(SEED_SPELLINGS)
        for right in SEED_SPELLINGS[index + 1 :]
    }
    reached = [
        pair for pair, verdict in verdicts.items() if verdict and verdict.confidence >= AUTO_MERGE
    ]

    assert len(reached) >= 2, verdicts


def test_nothing_the_corpus_calls_different_gets_merged() -> None:
    result = corpus.measure(AUTO_MERGE)

    assert result.false_positives == 0
    assert result.precision == 1.0


def test_no_cluster_mixes_two_merchants() -> None:
    report = corpus.cluster_report(AUTO_MERGE)

    assert report.contaminated == []


def test_the_matcher_still_resolves_what_it_resolved() -> None:
    report = corpus.cluster_report(AUTO_MERGE)

    assert len(report.united) >= 8
    assert report.attribution >= 0.84


def test_below_the_threshold_the_corpus_does_get_contaminated() -> None:
    assert corpus.cluster_report(0.75).contaminated != []
