from __future__ import annotations

from dataclasses import asdict, dataclass

from hub.declare import (
    Ask,
    Capability,
    Choice,
    Offer,
    Provider,
    Secret,
    Setting,
    Sync,
)
from hub.providers import (
    agendas,
    apple_health,
    bitvavo,
    books,
    claude,
    enable_banking,
    films,
    food,
    football,
    formula1,
    fx,
    github,
    google_health,
    holidays,
    ical,
    imap,
    ine,
    maps,
    nearby,
    places,
    podcasts,
    prices,
    routes,
    weather,
    wikimedia,
)

__all__ = [
    "Ask",
    "Capability",
    "Choice",
    "Offer",
    "Provider",
    "Secret",
    "Setting",
    "Sync",
]


@dataclass(frozen=True)
class Category:
    id: str
    name: str


CATEGORIES = (
    Category("finance", "Finanzas"),
    Category("ai", "IA"),
    Category("food", "Alimentación"),
    Category("health", "Salud"),
    Category("places", "Lugares"),
    Category("books", "Libros"),
    Category("calendar", "Calendario"),
    Category("notes", "Notas"),
    Category("economy", "Economía"),
    Category("leisure", "Ocio"),
    Category("weather", "Tiempo"),
)

GROUPS = (
    Category("sport", "Deporte"),
    Category("holidays", "Festivos"),
    Category("other", "Otros calendarios"),
    Category("leisure", "Agendas"),
)

MODULES = (
    apple_health,
    google_health,
    enable_banking,
    bitvavo,
    imap,
    fx,
    claude,
    food,
    books,
    places,
    nearby,
    maps,
    routes,
    weather,
    wikimedia,
    podcasts,
    films,
    holidays,
    formula1,
    football,
    ical,
    github,
    ine,
    prices,
    agendas,
)

PROVIDERS: tuple[Provider, ...] = tuple(one for module in MODULES for one in module.SOURCES)

BY_ID = {provider.id: provider for provider in PROVIDERS}

APPS = {
    "money": "Money",
    "chuping": "Chuping",
    "recipes": "Recipes",
    "planner": "Planner",
}


def offered(contracts: set[str] | None = None) -> list[Provider]:
    return [
        one
        for one in PROVIDERS
        if one.offer is not None
        and one.available
        and (contracts is None or contracts & set(one.emits))
    ]


def offer_of(provider: Provider) -> dict:
    assert provider.offer is not None
    return {"provider": provider.id, "produces": list(provider.emits), **asdict(provider.offer)}


def provider(provider_id: str) -> Provider:
    try:
        return BY_ID[provider_id]
    except KeyError:
        raise LookupError(f"arga no conoce el proveedor '{provider_id}'") from None


def listed() -> list[dict]:
    return [
        {
            "id": category.id,
            "name": category.name,
            "providers": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "capabilities": list(item.capabilities),
                    "available": item.available,
                    "single": item.single,
                    "lives_in": APPS.get(item.lives_in) if item.lives_in else None,
                    "created_in": APPS.get(item.created_in) if item.created_in else None,
                    "authorizes": item.authorizes,
                    "oauth": item.oauth,
                    "daily_budget": item.daily_budget,
                    "secrets": [
                        {
                            "key": secret.key,
                            "label": secret.label,
                            "help": secret.help,
                            "multiline": secret.multiline,
                        }
                        for secret in item.secrets
                    ],
                    "settings": [
                        {
                            "key": setting.key,
                            "label": setting.label,
                            "help": setting.help,
                            "default": setting.default,
                        }
                        for setting in item.settings
                    ],
                    "emits": list(item.emits),
                    "offer": offer_of(item) if item.offer is not None and item.available else None,
                }
                for item in PROVIDERS
                if item.category == category.id
            ]
            + by_mail(category.id),
        }
        for category in CATEGORIES
        if any(item.category == category.id for item in PROVIDERS) or by_mail(category.id)
    ]


def by_mail(category: str) -> list[dict]:
    from hub.extractors import EXTRACTORS

    return [
        {
            "id": f"imap.{extractor.id}",
            "name": extractor.entity,
            "description": f"Por correo: reenvía sus avisos a tu buzón y {extractor.entity} "
            "entra sola.",
            "capabilities": ["sync"],
            "available": False,
            "single": False,
            "lives_in": None,
            "created_in": None,
            "authorizes": False,
            "daily_budget": None,
            "by_mail": True,
            "secrets": [],
            "settings": [],
        }
        for extractor in EXTRACTORS.values()
        if extractor.category == category
    ]
