from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import arga_nutrients
from recipes.catalog import t

TBSP_ML = 15.0
TSP_ML = 5.0
PINCH_G = 0.5


@dataclass(frozen=True)
class Convertible:
    density_g_ml: float | None = None
    grams_per_unit: float | None = None
    portions: Mapping[str, float] = field(default_factory=dict)
    edible_fraction: float | None = None


def to_grams(
    quantity: float,
    unit: str,
    food: Convertible | None,
    portion: str | None = None,
    as_purchased: bool = False,
) -> float | None:
    raw = _raw_grams(quantity, unit, food, portion)
    if raw is None or not as_purchased or food is None or food.edible_fraction is None:
        return raw
    return raw * food.edible_fraction


def _raw_grams(
    quantity: float, unit: str, food: Convertible | None, portion: str | None
) -> float | None:
    if quantity <= 0:
        return 0.0
    if unit == "g":
        return quantity
    if unit == "pinch":
        return quantity * PINCH_G
    if food is None:
        return None
    if unit == "unit":
        if portion is not None:
            grams = food.portions.get(portion.strip().lower())
            return None if grams is None else quantity * grams
        if food.grams_per_unit is None:
            return None
        return quantity * food.grams_per_unit

    millilitres = {"ml": quantity, "tbsp": quantity * TBSP_ML, "tsp": quantity * TSP_ML}.get(unit)
    if millilitres is None or food.density_g_ml is None:
        return None
    return millilitres * food.density_g_ml


@dataclass(frozen=True)
class Per100g:
    kcal: float
    protein: float
    fat: float
    carbs: float
    fiber: float | None = None
    salt: float | None = None


@dataclass(frozen=True)
class Item:
    quantity: float
    unit: str
    macros: Per100g | None = None
    measures: Convertible | None = None
    label: str = ""
    nutrients: Mapping[str, float] | None = None
    portion: str | None = None
    as_purchased: bool = False
    per_unit: bool = False


@dataclass(frozen=True)
class Totals:
    kcal: float
    protein: float
    fat: float
    carbs: float
    fiber: float | None
    salt: float | None
    grams: float
    counted: int
    total: int
    missing: tuple[str, ...]
    nutrients: dict[str, float] = field(default_factory=dict)
    coverage: dict[str, float] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.missing


def _round(value: float) -> float:
    return round(value, 1)


def totals(items: list[Item], scale: float = 1.0) -> Totals:
    kcal = protein = fat = carbs = grams = 0.0
    fiber = salt = 0.0
    fiber_known = salt_known = False
    counted = 0
    missing: list[str] = []
    summed: list[tuple[float, Mapping[str, float], float]] = []

    for item in items:
        if item.per_unit:
            if item.unit != "unit" or item.macros is None:
                missing.append(item.label)
                continue
            share = item.quantity * scale
            per_one = item.measures.grams_per_unit if item.measures else None
            weight = share * (per_one or 0.0)
        else:
            converted = to_grams(
                item.quantity * scale, item.unit, item.measures, item.portion, item.as_purchased
            )
            if converted is None or item.macros is None:
                missing.append(item.label)
                continue
            weight = converted
            share = weight / 100.0
        summed.append((weight, item.nutrients or per_100g(None, item.macros), share))
        kcal += item.macros.kcal * share
        protein += item.macros.protein * share
        fat += item.macros.fat * share
        carbs += item.macros.carbs * share
        grams += weight
        if item.macros.fiber is not None:
            fiber += item.macros.fiber * share
            fiber_known = True
        if item.macros.salt is not None:
            salt += item.macros.salt * share
            salt_known = True
        counted += 1

    return Totals(
        kcal=_round(kcal),
        protein=_round(protein),
        fat=_round(fat),
        carbs=_round(carbs),
        fiber=_round(fiber) if fiber_known else None,
        salt=round(salt, 2) if salt_known else None,
        grams=_round(grams),
        counted=counted,
        total=len(items),
        missing=tuple(missing),
        **_micros(summed),
    )


def per_100g(
    stored: Mapping[str, Any] | None,
    macros: Per100g,
    lent: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    found = {
        key: value
        for key, value in arga_nutrients.only_known(lent or {}).items()
        if key not in arga_nutrients.MACROS
    }
    found.update(arga_nutrients.only_known(stored or {}))
    found.update(
        {"kcal": macros.kcal, "protein": macros.protein, "fat": macros.fat, "carbs": macros.carbs}
    )
    if macros.fiber is not None:
        found["fiber"] = macros.fiber
    if macros.salt is not None and "sodium" not in found:
        found["sodium"] = arga_nutrients.sodium_from_salt(macros.salt) or 0.0
    return found


def _micros(summed: list[tuple[float, Mapping[str, float], float]]) -> dict[str, Any]:
    parts = [(grams, arga_nutrients.scaled(basis, share * 100)) for grams, basis, share in summed]
    total = arga_nutrients.added(*(scaled for _, scaled in parts))
    kcal = total.get("kcal", 0.0)

    def weight(grams: float, scaled: Mapping[str, float]) -> float:
        return scaled.get("kcal", 0.0) if kcal > 0 else grams

    whole = sum(weight(grams, scaled) for grams, scaled in parts)
    coverage = {}
    for key in total:
        having = sum(
            weight(g, scaled)
            for (g, scaled), (_, basis, _) in zip(parts, summed, strict=True)
            if key in basis
        )
        coverage[key] = round(having / whole, 3) if whole > 0 else 1.0
    return {
        "nutrients": {key: round(value, 3) for key, value in total.items()},
        "coverage": coverage,
    }


def per_serving(total: Totals, servings: int) -> Totals:
    if servings < 1:
        raise ValueError("a recipe is for at least one person")
    return Totals(
        kcal=_round(total.kcal / servings),
        protein=_round(total.protein / servings),
        fat=_round(total.fat / servings),
        carbs=_round(total.carbs / servings),
        fiber=None if total.fiber is None else _round(total.fiber / servings),
        salt=None if total.salt is None else round(total.salt / servings, 2),
        grams=_round(total.grams / servings),
        counted=total.counted,
        total=total.total,
        missing=total.missing,
        nutrients={key: round(value / servings, 3) for key, value in total.nutrients.items()},
        coverage=dict(total.coverage),
    )


def uncertainty(total: Totals) -> str | None:
    if not total.missing:
        return None
    named = ", ".join(name for name in total.missing if name)
    missing = len(total.missing)
    key = "nutrition.missing.one" if missing == 1 else "nutrition.missing.other"
    count = t(key, count=missing, total=total.total)
    return f"{count} ({named})" if named else count
