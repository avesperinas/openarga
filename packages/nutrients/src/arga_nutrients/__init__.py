from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

Unit = Literal["kcal", "g", "mg", "µg"]
Group = Literal["energy", "macro", "fat", "mineral", "vitamin", "other"]


@dataclass(frozen=True)
class Nutrient:
    key: str
    name: str
    unit: Unit
    usda: tuple[int, ...]
    off: str | None
    group: Group
    front: bool = False
    digits: int = 1


NUTRIENTS: tuple[Nutrient, ...] = (
    Nutrient("kcal", "Energy", "kcal", (1008, 2048, 2047), "energy-kcal", "energy", True, 0),
    Nutrient("protein", "Protein", "g", (1003,), "proteins", "macro", True),
    Nutrient("carbs", "Carbohydrates", "g", (1005,), "carbohydrates", "macro", True),
    Nutrient("fat", "Fat", "g", (1004,), "fat", "macro", True),
    Nutrient("fiber", "Fiber", "g", (1079,), "fiber", "macro", True),
    Nutrient("sugars", "Sugars", "g", (2000, 1063), "sugars", "macro", True),
    Nutrient("saturated_fat", "Saturated fat", "g", (1258,), "saturated-fat", "fat", True),
    Nutrient("cholesterol", "Cholesterol", "mg", (1253,), "cholesterol", "fat", True, 0),
    Nutrient("sodium", "Sodium", "mg", (1093,), "sodium", "mineral", True, 0),
    Nutrient("potassium", "Potassium", "mg", (1092,), "potassium", "mineral", True, 0),
    Nutrient("calcium", "Calcium", "mg", (1087,), "calcium", "mineral", True, 0),
    Nutrient("iron", "Iron", "mg", (1089,), "iron", "mineral", True),
    Nutrient("magnesium", "Magnesium", "mg", (1090,), "magnesium", "mineral", True, 0),
    Nutrient("zinc", "Zinc", "mg", (1095,), "zinc", "mineral", True),
    Nutrient("vitamin_a", "Vitamin A", "µg", (1106,), "vitamin-a", "vitamin", True, 0),
    Nutrient("vitamin_c", "Vitamin C", "mg", (1162,), "vitamin-c", "vitamin", True, 0),
    Nutrient("vitamin_d", "Vitamin D", "µg", (1114,), "vitamin-d", "vitamin", True),
    Nutrient("vitamin_b12", "Vitamin B12", "µg", (1178,), "vitamin-b12", "vitamin", True),
    Nutrient("folate", "Folate", "µg", (1190, 1177), "folates", "vitamin", True, 0),
    Nutrient("caffeine", "Caffeine", "mg", (1057,), "caffeine", "other", True, 0),
    Nutrient("alcohol", "Alcohol", "g", (1018,), "alcohol", "other", True),
    Nutrient("starch", "Starch", "g", (1009,), "starch", "macro"),
    Nutrient("added_sugars", "Added sugars", "g", (1235,), "added-sugars", "macro"),
    Nutrient("fructose", "Fructose", "g", (1012,), "fructose", "macro"),
    Nutrient("lactose", "Lactose", "g", (1013,), "lactose", "macro"),
    Nutrient(
        "monounsaturated_fat", "Monounsaturated fat", "g", (1292,), "monounsaturated-fat", "fat"
    ),
    Nutrient(
        "polyunsaturated_fat", "Polyunsaturated fat", "g", (1293,), "polyunsaturated-fat", "fat"
    ),
    Nutrient("trans_fat", "Trans fat", "g", (1257,), "trans-fat", "fat", digits=2),
    Nutrient("omega3_ala", "Omega-3 (ALA)", "g", (1404,), "alpha-linolenic-acid", "fat", digits=2),
    Nutrient("omega3_epa", "Omega-3 (EPA)", "g", (1278,), "eicosapentaenoic-acid", "fat", digits=2),
    Nutrient("omega3_dha", "Omega-3 (DHA)", "g", (1272,), "docosahexaenoic-acid", "fat", digits=2),
    Nutrient("phosphorus", "Phosphorus", "mg", (1091,), "phosphorus", "mineral", digits=0),
    Nutrient("copper", "Copper", "mg", (1098,), "copper", "mineral", digits=2),
    Nutrient("manganese", "Manganese", "mg", (1101,), "manganese", "mineral", digits=2),
    Nutrient("selenium", "Selenium", "µg", (1103,), "selenium", "mineral"),
    Nutrient("iodine", "Iodine", "µg", (1100,), "iodine", "mineral", digits=0),
    Nutrient("fluoride", "Fluoride", "µg", (1099,), "fluoride", "mineral", digits=0),
    Nutrient("vitamin_e", "Vitamin E", "mg", (1109,), "vitamin-e", "vitamin"),
    Nutrient("vitamin_k", "Vitamin K", "µg", (1185,), "vitamin-k", "vitamin"),
    Nutrient("thiamin", "Thiamin (B1)", "mg", (1165,), "vitamin-b1", "vitamin", digits=2),
    Nutrient("riboflavin", "Riboflavin (B2)", "mg", (1166,), "vitamin-b2", "vitamin", digits=2),
    Nutrient("niacin", "Niacin (B3)", "mg", (1167,), "vitamin-pp", "vitamin"),
    Nutrient(
        "pantothenic_acid",
        "Pantothenic acid (B5)",
        "mg",
        (1170,),
        "pantothenic-acid",
        "vitamin",
        digits=2,
    ),
    Nutrient("vitamin_b6", "Vitamin B6", "mg", (1175,), "vitamin-b6", "vitamin", digits=2),
    Nutrient("biotin", "Biotin (B8)", "µg", (1176,), "biotin", "vitamin"),
    Nutrient("choline", "Choline", "mg", (1180,), "choline", "vitamin", digits=0),
    Nutrient("retinol", "Retinol", "µg", (1105,), None, "vitamin", digits=0),
    Nutrient("beta_carotene", "Beta-carotene", "µg", (1107,), "beta-carotene", "vitamin", digits=0),
    Nutrient("lycopene", "Lycopene", "µg", (1122,), None, "other", digits=0),
    Nutrient("lutein_zeaxanthin", "Lutein and zeaxanthin", "µg", (1123,), None, "other", digits=0),
    Nutrient("theobromine", "Theobromine", "mg", (1058,), None, "other", digits=0),
    Nutrient("water", "Water", "g", (1051,), None, "other"),
)

BY_KEY: dict[str, Nutrient] = {one.key: one for one in NUTRIENTS}
KEYS: frozenset[str] = frozenset(BY_KEY)
FRONT: tuple[Nutrient, ...] = tuple(one for one in NUTRIENTS if one.front)
MACROS = ("kcal", "protein", "carbs", "fat")

SALT_PER_SODIUM = 2.5
KJ_PER_KCAL = 4.184
ETHANOL_G_PER_ML = 0.789
FROM_GRAMS = {"g": 1.0, "mg": 1_000.0, "µg": 1_000_000.0}


def _clean(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def from_usda(food_nutrients: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    by_id: dict[int, float] = {}
    for item in food_nutrients:
        nested = item.get("nutrient") if isinstance(item.get("nutrient"), Mapping) else {}
        number = item.get("nutrientId") or nested.get("id")
        value = _clean(item.get("value", item.get("amount")))
        if number is None or value is None:
            continue
        try:
            by_id[int(number)] = value
        except (TypeError, ValueError):
            continue
    found: dict[str, float] = {}
    for nutrient in NUTRIENTS:
        for number in nutrient.usda:
            if number in by_id:
                found[nutrient.key] = by_id[number]
                break
    return found


def from_off(nutriments: Mapping[str, Any]) -> dict[str, float]:
    found: dict[str, float] = {}
    for nutrient in NUTRIENTS:
        if nutrient.off is None:
            continue
        value = _clean(nutriments.get(f"{nutrient.off}_100g"))
        if nutrient.key == "kcal":
            if value is None:
                kj = _clean(nutriments.get("energy-kj_100g", nutriments.get("energy_100g")))
                value = None if kj is None else round(kj / KJ_PER_KCAL, 1)
        elif nutrient.key == "alcohol":
            value = None if value is None else round(value * ETHANOL_G_PER_ML, 2)
        elif value is not None:
            value = value * FROM_GRAMS[nutrient.unit]
        if value is not None:
            found[nutrient.key] = round(value, 4)
    if "sodium" not in found:
        salt = _clean(nutriments.get("salt_100g"))
        if salt is not None:
            found["sodium"] = round(salt / SALT_PER_SODIUM * 1_000, 2)
    return found


def salt_from_sodium(sodium_mg: float | None) -> float | None:
    return None if sodium_mg is None else round(sodium_mg * SALT_PER_SODIUM / 1_000, 3)


def sodium_from_salt(salt_g: float | None) -> float | None:
    return None if salt_g is None else round(salt_g / SALT_PER_SODIUM * 1_000, 2)


def only_known(values: Mapping[str, Any]) -> dict[str, float]:
    found = {}
    for key, value in values.items():
        number = _clean(value)
        if key in KEYS and number is not None:
            found[key] = number
    return found


MASS_UNITS = {"g": 1.0, "mg": 1e-3, "µg": 1e-6, "ug": 1e-6, "mcg": 1e-6, "μg": 1e-6}
ENERGY_UNITS = {"kcal": 1.0, "kj": 1 / KJ_PER_KCAL}
MAX_KCAL_100G = 1000.0


class Invalid(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _amount(key: str, raw: Any) -> float:
    nutrient = BY_KEY[key]
    if isinstance(raw, Mapping):
        amount = _clean(raw.get("amount"))
        unit = str(raw.get("unit") or nutrient.unit).strip()
    else:
        amount, unit = _clean(raw), nutrient.unit
    if amount is None:
        raise ValueError(f"{key}: no es un número mayor o igual que cero")
    if nutrient.unit == "kcal":
        factor = ENERGY_UNITS.get(unit.lower())
        if factor is None:
            raise ValueError(f"{key}: va en kcal o kJ, no en {unit}")
        return amount * factor
    to_grams = MASS_UNITS.get(unit if unit in MASS_UNITS else unit.lower())
    if to_grams is None:
        raise ValueError(f"{key}: va en {nutrient.unit} (o g, mg, µg), no en {unit}")
    return amount * to_grams * FROM_GRAMS[nutrient.unit]


def typed(values: Mapping[str, Any], *, per: float = 100.0) -> dict[str, float]:
    found: dict[str, float] = {}
    problems: list[str] = []
    for key, raw in values.items():
        if key not in BY_KEY:
            problems.append(f"'{key}' no es un nutriente de arga (mira `list_nutrients`)")
            continue
        try:
            value = _amount(key, raw)
        except ValueError as error:
            problems.append(str(error))
            continue
        nutrient = BY_KEY[key]
        if nutrient.unit == "kcal":
            if value > MAX_KCAL_100G * per / 100:
                problems.append(f"{key}: {value:g} kcal en {per:g} g no puede ser")
        elif value / FROM_GRAMS[nutrient.unit] > per:
            problems.append(f"{key}: {value:g} {nutrient.unit} pesa más que los {per:g} g")
        found[key] = round(value, 6)
    if problems:
        raise Invalid(problems)
    return found


def catalogue() -> list[dict[str, Any]]:
    return [
        {"key": one.key, "name": one.name, "unit": one.unit, "group": one.group}
        for one in NUTRIENTS
    ]


def scaled(per_100g: Mapping[str, float], grams: float) -> dict[str, float]:
    share = grams / 100.0
    return {key: round(value * share, 4) for key, value in per_100g.items()}


def added(*many: Mapping[str, float]) -> dict[str, float]:
    total: dict[str, float] = {}
    for one in many:
        for key, value in one.items():
            total[key] = round(total.get(key, 0.0) + value, 4)
    return total


Kind = Literal["min", "max", "energy_share"]
Sex = Literal["female", "male"]


@dataclass(frozen=True)
class Reference:
    key: str
    kind: Kind
    value: float


DEFAULT_AGE = 40

_EFSA: tuple[tuple[str, Kind, float, float, float], ...] = (
    ("fiber", "min", 25, 25, 25),
    ("potassium", "min", 3500, 3500, 3500),
    ("magnesium", "min", 350, 300, 300),
    ("iron", "min", 11, 16, 11),
    ("zinc", "min", 11.7, 8.9, 8.9),
    ("vitamin_a", "min", 750, 650, 650),
    ("vitamin_c", "min", 110, 95, 95),
    ("vitamin_d", "min", 15, 15, 15),
    ("vitamin_b12", "min", 4, 4, 4),
    ("folate", "min", 330, 330, 330),
    ("phosphorus", "min", 550, 550, 550),
    ("copper", "min", 1.6, 1.3, 1.3),
    ("manganese", "min", 3, 3, 3),
    ("selenium", "min", 70, 70, 70),
    ("iodine", "min", 150, 150, 150),
    ("vitamin_e", "min", 13, 11, 11),
    ("vitamin_k", "min", 70, 70, 70),
    ("riboflavin", "min", 1.6, 1.6, 1.6),
    ("pantothenic_acid", "min", 5, 5, 5),
    ("vitamin_b6", "min", 1.7, 1.6, 1.6),
    ("biotin", "min", 40, 40, 40),
    ("choline", "min", 400, 400, 400),
    ("sodium", "max", 2000, 2000, 2000),
    ("caffeine", "max", 400, 400, 400),
    ("saturated_fat", "energy_share", 0.10, 0.10, 0.10),
    ("sugars", "energy_share", 0.10, 0.10, 0.10),
)


def age_on(birth_date: date | None, today: date) -> int | None:
    if birth_date is None:
        return None
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def references(sex: str | None, age: int | None) -> dict[str, Reference]:
    age = DEFAULT_AGE if age is None else age
    found: dict[str, Reference] = {}
    for key, kind, man, young_woman, older_woman in _EFSA:
        woman = young_woman if age < 50 else older_woman
        if sex == "male":
            value = man
        elif sex == "female":
            value = woman
        else:
            value = max(man, woman) if kind == "min" else min(man, woman)
        found[key] = Reference(key, kind, float(value))
    found["calcium"] = Reference("calcium", "min", 1000.0 if age < 25 else 950.0)
    return found


Basis = Literal["amount", "kcal_pct"]

KCAL_PER_GRAM: dict[str, float] = {
    "protein": 4.0,
    "carbs": 4.0,
    "fat": 9.0,
    "fiber": 2.0,
    "sugars": 4.0,
    "added_sugars": 4.0,
    "starch": 4.0,
    "saturated_fat": 9.0,
    "monounsaturated_fat": 9.0,
    "polyunsaturated_fat": 9.0,
    "trans_fat": 9.0,
    "alcohol": 7.0,
}
PROTEIN_G_PER_KG = 0.83


@dataclass(frozen=True)
class Goal:
    key: str
    basis: Basis
    min: float | None
    max: float | None


def default_goals(sex: str | None, age: int | None, weight_kg: float | None) -> dict[str, Goal]:
    found: dict[str, Goal] = {}
    for key, one in references(sex, age).items():
        if one.kind == "min":
            found[key] = Goal(key, "amount", one.value, None)
        elif one.kind == "max":
            found[key] = Goal(key, "amount", None, one.value)
        else:
            found[key] = Goal(key, "kcal_pct", None, round(one.value * 100, 3))
    found["fat"] = Goal("fat", "kcal_pct", 20.0, 35.0)
    found["carbs"] = Goal("carbs", "kcal_pct", 45.0, 60.0)
    if weight_kg:
        found["protein"] = Goal("protein", "amount", round(PROTEIN_G_PER_KG * weight_kg, 1), None)
    return found


__all__ = [
    "BY_KEY",
    "DEFAULT_AGE",
    "FRONT",
    "Goal",
    "Invalid",
    "KCAL_PER_GRAM",
    "KEYS",
    "MACROS",
    "NUTRIENTS",
    "Nutrient",
    "Reference",
    "added",
    "age_on",
    "catalogue",
    "default_goals",
    "from_off",
    "from_usda",
    "only_known",
    "references",
    "salt_from_sodium",
    "scaled",
    "sodium_from_salt",
    "typed",
]
