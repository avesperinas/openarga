from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

import arga_nutrients as nutrients
from hub.declare import Provider, Secret
from hub.providers import USER_AGENT

USDA_SEARCH = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_FOODS = "https://api.nal.usda.gov/fdc/v1/foods"
OFF_SEARCH = "https://search.openfoodfacts.org/search"
OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"


def timeout() -> float:
    return float(os.environ.get("FOOD_SOURCE_TIMEOUT_SECONDS", "10"))


RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def attempts() -> int:
    return max(1, int(os.environ.get("FOOD_SOURCE_ATTEMPTS", "3")))


def backoff() -> float:
    return float(os.environ.get("FOOD_SOURCE_BACKOFF_SECONDS", "0.5"))


def budget() -> float:
    return float(os.environ.get("FOOD_SOURCE_BUDGET_SECONDS", "20"))


async def send(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> httpx.Response:
    deadline = time.monotonic() + budget()
    tries = attempts()
    for attempt in range(tries):
        left = deadline - time.monotonic()
        try:
            response = await client.request(
                method, url, timeout=max(0.5, min(timeout(), left)), **kwargs
            )
        except httpx.TransportError:
            response = None
            if attempt == tries - 1:
                raise
        else:
            if response.status_code not in RETRY_STATUSES or attempt == tries - 1:
                return response
        wait = backoff() * 2**attempt
        if time.monotonic() + wait >= deadline:
            if response is None:
                raise httpx.ConnectTimeout("sin plazo para otro intento")
            return response
        await asyncio.sleep(wait)
    raise AssertionError("unreachable")


CACHE_ENTRIES = 512
_cache: OrderedDict[tuple[str, str, int], tuple[float, list[Candidate]]] = OrderedDict()


def cache_seconds() -> float:
    return float(os.environ.get("FOOD_SEARCH_CACHE_SECONDS", "21600"))


def _cache_key(source: str, query: str, limit: int) -> tuple[str, str, int]:
    return (source, " ".join(query.lower().split()), limit)


def cached(source: str, query: str, limit: int) -> list[Candidate] | None:
    key = _cache_key(source, query, limit)
    found = _cache.get(key)
    if found is None:
        return None
    expires, candidates = found
    if expires < time.monotonic():
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return candidates


def remember(source: str, query: str, limit: int, candidates: list[Candidate]) -> None:
    _cache[_cache_key(source, query, limit)] = (time.monotonic() + cache_seconds(), candidates)
    _cache.move_to_end(_cache_key(source, query, limit))
    while len(_cache) > CACHE_ENTRIES:
        _cache.popitem(last=False)


def forget() -> None:
    _cache.clear()


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
    portions: list[dict[str, Any]] = field(default_factory=list)


class SourceFailed(Exception):
    pass


MAX_KCAL_100G = 1000.0
MAX_MACROS_100G = 110.0


def implausible(candidate: Candidate) -> str | None:
    if candidate.kcal_100g > MAX_KCAL_100G:
        return f"{candidate.kcal_100g:g} kcal por 100 g"
    grams = {
        "proteína": candidate.protein_100g,
        "grasa": candidate.fat_100g,
        "hidratos": candidate.carbs_100g,
        "fibra": candidate.fiber_100g,
        "sal": candidate.salt_100g,
    }
    if candidate.kcal_100g < 0:
        return f"{candidate.kcal_100g:g} kcal por 100 g"
    for name, value in grams.items():
        if value is not None and not 0 <= value <= 100:
            return f"{value:g} g de {name} por 100 g"
    if candidate.protein_100g + candidate.fat_100g + candidate.carbs_100g > MAX_MACROS_100G:
        return "sus macros suman más de 100 g por 100 g"
    return None


def sieve(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict[str, str]]]:
    kept: list[Candidate] = []
    dropped: list[dict[str, str]] = []
    for candidate in candidates:
        reason = implausible(candidate)
        if reason is None:
            kept.append(candidate)
        else:
            dropped.append({"source": candidate.source, "name": candidate.name, "reason": reason})
    return kept, dropped


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


MAX_PORTION_G = 5000.0


def _grams(value: Any, unit: Any = "g") -> float | None:
    try:
        grams = float(value)
    except (TypeError, ValueError):
        return None
    if str(unit or "g").strip().lower() not in ("g", "gr", "gram", "grams", "grm"):
        return None
    return round(grams, 1) if 0 < grams <= MAX_PORTION_G else None


def portions(package: float | None, serving: float | None) -> list[dict[str, Any]]:
    found = []
    if package:
        found.append({"name": "envase", "grams": package})
    if serving and serving != package:
        found.append({"name": "ración", "grams": serving})
    return found


USDA_NUTRIENTS = {1008: "kcal_100g", 1003: "protein_100g", 1004: "fat_100g", 1005: "carbs_100g"}
USDA_FIBER = 1079
USDA_SODIUM = 1093
SALT_PER_SODIUM = 2.5


def _usda_macros(food: dict) -> dict[str, float | None]:
    found: dict[str, float | None] = {}
    for nutrient in food.get("foodNutrients") or []:
        number = nutrient.get("nutrientId") or nutrient.get("nutrientNumber")
        value = nutrient.get("value")
        if value is None:
            continue
        if number in USDA_NUTRIENTS:
            found[USDA_NUTRIENTS[number]] = float(value)
        elif number == USDA_FIBER:
            found["fiber_100g"] = float(value)
        elif number == USDA_SODIUM:
            found["salt_100g"] = round(float(value) * SALT_PER_SODIUM / 1000, 3)
    return found


async def search_usda(
    client: httpx.AsyncClient, key: str, query: str, limit: int = 10
) -> list[Candidate]:
    if not key:
        raise SourceFailed("sin clave de USDA: ponla en Hub")
    try:
        response = await send(
            client,
            "GET",
            USDA_SEARCH,
            params={
                "query": query,
                "api_key": key,
                "pageSize": limit,
                "dataType": "Foundation,SR Legacy",
            },
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"USDA no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("USDA contestó algo que no es JSON") from error

    candidates = []
    for food in payload.get("foods") or []:
        candidate = _usda_found(food)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _usda_found(food: Any) -> Candidate | None:
    try:
        macros = _usda_macros(food)
        if not all(key in macros for key in USDA_NUTRIENTS.values()):
            return None
        return Candidate(
            source="usda",
            source_ref=str(food["fdcId"]),
            name=str(food.get("description") or "").strip(),
            category_hint=category_hint(food.get("foodCategory"), food.get("description")),
            nutrients=nutrients.from_usda(food.get("foodNutrients") or []),
            portions=_usda_portions(food),
            **macros,  # type: ignore[arg-type]
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _usda_portions(food: dict) -> list[dict[str, Any]]:
    serving = _grams(food.get("servingSize"), food.get("servingSizeUnit"))
    if serving is None:
        for one in food.get("foodPortions") or []:
            if not isinstance(one, dict) or float(one.get("amount") or 1) != 1:
                continue
            serving = _grams(one.get("gramWeight"))
            if serving is not None:
                break
    return portions(None, serving)


def _usda_detail(food: dict) -> Candidate | None:
    found = nutrients.from_usda(food.get("foodNutrients") or [])
    if not all(key in found for key in nutrients.MACROS):
        return None
    category = food.get("foodCategory")
    if isinstance(category, dict):
        category = category.get("description")
    return Candidate(
        source="usda",
        source_ref=str(food["fdcId"]),
        name=str(food.get("description") or "").strip(),
        kcal_100g=found["kcal"],
        protein_100g=found["protein"],
        fat_100g=found["fat"],
        carbs_100g=found["carbs"],
        fiber_100g=found.get("fiber"),
        salt_100g=nutrients.salt_from_sodium(found.get("sodium")),
        category_hint=category_hint(category, food.get("description")),
        nutrients=found,
        portions=_usda_portions(food),
    )


async def get_usda(client: httpx.AsyncClient, key: str, refs: list[str]) -> list[Candidate]:
    if not key:
        raise SourceFailed("sin clave de USDA: ponla en Hub")
    ids = [int(ref) for ref in refs if ref.isdigit()]
    if not ids:
        return []
    try:
        response = await send(
            client,
            "POST",
            USDA_FOODS,
            params={"api_key": key},
            json={"fdcIds": ids, "format": "full"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as error:
        raise SourceFailed(f"USDA no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("USDA contestó algo que no es JSON") from error
    found = [_usda_detail(food) for food in payload if isinstance(food, dict)]
    return [candidate for candidate in found if candidate is not None]


OFF_FIELDS = (
    "code,product_name,brands,categories,nutriments,"
    "product_quantity,product_quantity_unit,serving_quantity,serving_quantity_unit"
)


KJ_PER_KCAL = 4.184


def _off_kcal(nutriments: dict) -> float:
    if nutriments.get("energy-kcal_100g") is not None:
        return float(nutriments["energy-kcal_100g"])
    kj = nutriments.get("energy-kj_100g", nutriments.get("energy_100g"))
    if kj is None:
        raise KeyError("energy-kcal_100g")
    return round(float(kj) / KJ_PER_KCAL, 1)


def _off_candidate(product: dict) -> Candidate | None:
    nutriments = product.get("nutriments") or {}
    name = str(product.get("product_name") or "").strip()
    code = str(product.get("code") or "").strip()
    if not name or not code:
        return None
    try:
        kcal = _off_kcal(nutriments)
        protein = float(nutriments["proteins_100g"])
        fat = float(nutriments["fat_100g"])
        carbs = float(nutriments["carbohydrates_100g"])
    except (KeyError, TypeError, ValueError):
        return None

    def optional(field: str) -> float | None:
        try:
            return float(nutriments[field])
        except (KeyError, TypeError, ValueError):
            return None

    brand = _first(product.get("brands"))
    categories = product.get("categories")
    if isinstance(categories, list):
        categories = ", ".join(str(one) for one in categories)
    return Candidate(
        source="off",
        source_ref=code,
        name=name,
        kcal_100g=kcal,
        protein_100g=protein,
        fat_100g=fat,
        carbs_100g=carbs,
        fiber_100g=optional("fiber_100g"),
        salt_100g=optional("salt_100g"),
        brand=brand,
        category_hint=category_hint(categories, name),
        nutrients=nutrients.from_off(nutriments),
        portions=portions(
            _grams(product.get("product_quantity"), product.get("product_quantity_unit")),
            _grams(product.get("serving_quantity"), product.get("serving_quantity_unit")),
        ),
    )


def _off_found(product: Any) -> Candidate | None:
    try:
        return _off_candidate(product)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _first(brands: object) -> str | None:
    if isinstance(brands, list):
        brands = brands[0] if brands else ""
    return str(brands or "").split(",")[0].strip() or None


def looks_like_barcode(query: str) -> bool:
    digits = query.strip()
    return digits.isdigit() and 8 <= len(digits) <= 14


async def search_off(client: httpx.AsyncClient, query: str, limit: int = 10) -> list[Candidate]:
    headers = {"user-agent": USER_AGENT}
    try:
        if looks_like_barcode(query):
            response = await send(
                client,
                "GET",
                OFF_PRODUCT.format(barcode=query.strip()),
                params={"fields": OFF_FIELDS},
                headers=headers,
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            product = response.json().get("product")
            found = [product] if product else []
        else:
            response = await send(
                client,
                "GET",
                OFF_SEARCH,
                params={
                    "q": query,
                    "langs": "es",
                    "page_size": limit,
                    "fields": OFF_FIELDS,
                },
                headers=headers,
            )
            response.raise_for_status()
            found = response.json().get("hits") or []
    except httpx.HTTPError as error:
        raise SourceFailed(f"OpenFoodFacts no contestó: {type(error).__name__}") from error
    except ValueError as error:
        raise SourceFailed("OpenFoodFacts contestó algo que no es JSON") from error

    candidates = [_off_found(product) for product in found]
    return [candidate for candidate in candidates if candidate is not None]


async def get_off(client: httpx.AsyncClient, codes: list[str]) -> list[Candidate]:
    found = []
    for code in codes:
        if looks_like_barcode(code):
            found.extend(await search_off(client, code, 1))
    return found


def normalise(key: str, raw: str) -> str:
    value = raw.strip()
    if not value or any(character.isspace() for character in value):
        raise ValueError("no parece una clave: pégala tal cual, sin espacios")
    return value


def as_dict(candidate: Candidate) -> dict:
    return asdict(candidate)


SOURCES = (
    Provider(
        id="usda",
        name="USDA FoodData Central",
        category="food",
        description="Las macros de los ingredientes genéricos, bajo demanda al escribir una "
        "receta.",
        capabilities=("lookup",),
        serves=("food.search", "food.get", "usda.handoff"),
        secrets=(
            Secret(
                "api_key",
                "Clave de API",
                "Gratis en api.data.gov/signup: te llega por correo.",
            ),
        ),
        available=True,
        single=True,
        normalise=normalise,
    ),
    Provider(
        id="openfoodfacts",
        name="Open Food Facts",
        category="food",
        description="Las macros de los productos de marca y por código de barras, bajo demanda. "
        "Sin clave: se conecta sola la primera vez que buscas.",
        capabilities=("lookup",),
        serves=("food.search", "food.get"),
        available=True,
        single=True,
    ),
)
