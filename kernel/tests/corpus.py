from __future__ import annotations

import sys
from dataclasses import dataclass
from itertools import combinations

from kernel.identity import Match, compare

CITIES = ("VALENCIA", "GANDIA", "XATIVA")
TRUNCATION = 22


@dataclass(frozen=True)
class Merchant:
    identity: str
    base: str
    abbreviation: str | None = None
    stores: tuple[str, ...] = ()


MERCHANTS = (
    Merchant("alba", "ALBA MARKET", "SUPERM. ALBA", ("221", "305")),
    Merchant("tilos", "PANADERIA LOS TILOS", None, ()),
    Merchant("km42", "E.S. KM-42 NORTE", "ES KM42", ("7",)),
    Merchant("valduerna", "FARMACIA VALDUERNA", None, ()),
    Merchant("valdemoro", "FARMACIA VALDEMORO", None, ()),
    Merchant("sauce_dental", "CLINICA DENTAL SAUCE", None, ("12",)),
    Merchant("sauce_bar", "BAR EL SAUCE", None, ()),
    Merchant("oriol_libros", "LIBRERIA ORIOL", None, ()),
    Merchant("oriol_taller", "TALLERES ORIOL", None, ()),
    Merchant("mirasol", "PASTELERIA MIRASOL", "PAST. MIRASOL", ("4",)),
    Merchant("norteclima", "NORTECLIMA INSTALACIONES", None, ("221",)),
)


def descriptors(merchant: Merchant) -> list[str]:
    forms = [merchant.base]
    if merchant.abbreviation:
        forms.append(merchant.abbreviation)

    written = []
    for index, form in enumerate(forms):
        written.append(form)
        written.append(f"COMPRA EN {form}")
        written.append(f"{form} SL" if index % 2 else f"{form} SA")
        written.append(f"{form} {CITIES[index % len(CITIES)]}")
        for position, store in enumerate(merchant.stores):
            written.append(f"{form} {store}" if position % 2 else f"{form} {store.zfill(4)}")
        truncated = f"{form} {CITIES[index % len(CITIES)]}"[:TRUNCATION].strip()
        if truncated not in written:
            written.append(truncated)

    return list(dict.fromkeys(written))


def labelled_pairs() -> list[tuple[str, str, bool]]:
    catalogue = [
        (merchant.identity, descriptor)
        for merchant in MERCHANTS
        for descriptor in descriptors(merchant)
    ]
    return [
        (left_text, right_text, left_identity == right_identity)
        for (left_identity, left_text), (right_identity, right_text) in combinations(catalogue, 2)
    ]


@dataclass(frozen=True)
class Measurement:
    threshold: float
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        decided = self.true_positives + self.false_positives
        return self.true_positives / decided if decided else 1.0

    @property
    def recall(self) -> float:
        actual = self.true_positives + self.false_negatives
        return self.true_positives / actual if actual else 1.0


def measure(threshold: float, pairs: list[tuple[str, str, bool]] | None = None) -> Measurement:
    true_positives = false_positives = false_negatives = 0
    for left, right, same in pairs if pairs is not None else labelled_pairs():
        verdict: Match | None = compare(left, right)
        merged = verdict is not None and verdict.confidence >= threshold
        if merged and same:
            true_positives += 1
        elif merged and not same:
            false_positives += 1
        elif not merged and same:
            false_negatives += 1
    return Measurement(threshold, true_positives, false_positives, false_negatives)


def mistakes(threshold: float) -> tuple[list[tuple[str, str, Match]], list[tuple[str, str]]]:
    wrong_merges: list[tuple[str, str, Match]] = []
    missed: list[tuple[str, str]] = []
    for left, right, same in labelled_pairs():
        verdict = compare(left, right)
        merged = verdict is not None and verdict.confidence >= threshold
        if merged and not same and verdict is not None:
            wrong_merges.append((left, right, verdict))
        elif not merged and same:
            missed.append((left, right))
    return wrong_merges, missed


def clusters(threshold: float) -> dict[str, set[str]]:
    catalogue = [
        (merchant.identity, descriptor)
        for merchant in MERCHANTS
        for descriptor in descriptors(merchant)
    ]
    parent = {descriptor: descriptor for _, descriptor in catalogue}

    def root(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for (_, left), (_, right) in combinations(catalogue, 2):
        verdict = compare(left, right)
        if verdict is not None and verdict.confidence >= threshold:
            parent[root(left)] = root(right)

    grouped: dict[str, set[str]] = {}
    for _, descriptor in catalogue:
        grouped.setdefault(root(descriptor), set()).add(descriptor)
    return grouped


@dataclass(frozen=True)
class ClusterReport:
    threshold: float
    united: list[str]
    split: dict[str, int]
    contaminated: list[tuple[str, ...]]
    attributed: int
    total: int

    @property
    def attribution(self) -> float:
        return self.attributed / self.total if self.total else 1.0


def cluster_report(threshold: float) -> ClusterReport:
    identity_of = {
        descriptor: merchant.identity
        for merchant in MERCHANTS
        for descriptor in descriptors(merchant)
    }
    groups = clusters(threshold)

    per_identity: dict[str, int] = {}
    contaminated = []
    for members in groups.values():
        identities = {identity_of[member] for member in members}
        if len(identities) > 1:
            contaminated.append(tuple(sorted(identities)))
        for identity in identities:
            per_identity[identity] = per_identity.get(identity, 0) + 1

    largest: dict[str, int] = {}
    for members in groups.values():
        for identity in {identity_of[member] for member in members}:
            own = sum(1 for member in members if identity_of[member] == identity)
            largest[identity] = max(largest.get(identity, 0), own)

    return ClusterReport(
        threshold=threshold,
        united=sorted(name for name, count in per_identity.items() if count == 1),
        split={name: count for name, count in sorted(per_identity.items()) if count > 1},
        contaminated=contaminated,
        attributed=sum(largest.values()),
        total=len(identity_of),
    )


THRESHOLDS = (0.7, 0.75, 0.8, 0.85, 0.9, 0.95)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    pairs = labelled_pairs()
    positives = sum(1 for *_, same in pairs if same)

    print(f"corpus · {len(MERCHANTS)} comercios · {len(pairs)} pares · {positives} del mismo")
    print(f"{'umbral':>7}  {'precisión':>10}  {'cobertura':>10}  {'de más':>7}  {'de menos':>9}")
    for threshold in THRESHOLDS:
        result = measure(threshold, pairs)
        print(
            f"{threshold:>7.2f}  {result.precision:>10.1%}  {result.recall:>10.1%}"
            f"  {result.false_positives:>7}  {result.false_negatives:>9}"
        )

    print()
    print(f"{'umbral':>7}  {'en 1 entidad':>13}  {'atribución':>11}  {'mezclados':>10}  partidos")
    for threshold in THRESHOLDS:
        report = cluster_report(threshold)
        split = ", ".join(f"{name}:{count}" for name, count in report.split.items()) or "-"
        print(
            f"{threshold:>7.2f}  {f'{len(report.united)}/{len(MERCHANTS)}':>13}"
            f"  {report.attribution:>11.1%}  {len(report.contaminated):>10}  {split}"
        )

    if arguments == ["--mistakes"]:
        for threshold in THRESHOLDS:
            wrong, missed = mistakes(threshold)
            print(f"\n=== umbral {threshold:.2f} ===")
            for left, right, verdict in wrong:
                print(f"  DE MÁS   {left!r} · {right!r} · {verdict.rule} {verdict.confidence}")
            for left, right in sorted({tuple(sorted(pair)) for pair in missed}):
                print(f"  DE MENOS {left!r} · {right!r}")
    elif arguments:
        print("uso: python -m kernel.corpus [--mistakes]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
