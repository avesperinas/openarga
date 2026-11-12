from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class Candidate:
    source: str
    source_ref: str
    name: str
    kcal_100g: float
    protein_100g: float
    fat_100g: float
    carbs_100g: float
    fiber_100g: float | None = None
    salt_100g: float | None = None
    brand: str | None = None
    category_hint: str = "other"
    nutrients: dict[str, float] = field(default_factory=dict)
    portions: list[dict] = field(default_factory=list)

    @classmethod
    def from_hub(cls, raw: dict) -> Candidate:
        known = {one.name for one in fields(cls)}
        return cls(**{key: value for key, value in raw.items() if key in known})


HINTS = {
    "vegetable": ("vegetable", "légume", "verdura", "legumbres-y-verduras"),
    "fruit": ("fruit", "fruta", "berries"),
    "protein": ("poultry", "beef", "pork", "sausage", "lamb", "meat", "carne", "embutido"),
    "fish": ("fish", "seafood", "shellfish", "pescado", "marisco", "poisson"),
    "dairy": ("dairy", "cheese", "yogurt", "milk", "egg", "lácteo", "queso", "huevo", "leche"),
    "grain": ("cereal", "grain", "pasta", "bread", "rice", "pan", "arroz", "harina"),
    "legume": ("legume", "bean", "lentil", "chickpea", "legumbre", "garbanzo", "lenteja"),
    "fat": ("fat", "oil", "butter", "aceite", "mantequilla", "grasa"),
    "spice": ("spice", "herb", "condiment", "sauce", "especia", "salsa", "condimento"),
    "sweet": ("sweet", "sugar", "candy", "chocolate", "dessert", "azúcar", "dulce", "postre"),
    "liquid": ("beverage", "drink", "broth", "soup", "bebida", "caldo", "zumo", "juice"),
}


def category_hint(*texts: str | None) -> str:
    haystack = " ".join(text.lower() for text in texts if text)
    for category, needles in HINTS.items():
        if any(needle in haystack for needle in needles):
            return category
    return "other"


def looks_like_barcode(query: str) -> bool:
    digits = query.strip()
    return digits.isdigit() and 8 <= len(digits) <= 14
