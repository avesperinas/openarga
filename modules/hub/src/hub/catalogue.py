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
from hub.words import local

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
    Category("finance", "Finance"),
    Category("ai", "AI"),
    Category("food", "Food"),
    Category("health", "Health"),
    Category("places", "Places"),
    Category("books", "Books"),
    Category("calendar", "Calendar"),
    Category("notes", "Notes"),
    Category("economy", "Economy"),
    Category("leisure", "Leisure"),
    Category("weather", "Weather"),
)

GROUPS = (
    Category("sport", "Sport"),
    Category("holidays", "Holidays"),
    Category("other", "Other calendars"),
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
    offer = asdict(provider.offer)
    base = f"provider.{provider.id}.offer"
    for field in ("title", "subtitle", "name"):
        offer[field] = local(f"{base}.{field}", offer[field])
    for ask in offer["asks"]:
        at = f"{base}.ask.{ask['key']}"
        for field in ("label", "help", "placeholder", "none_label"):
            ask[field] = local(f"{at}.{field}", ask[field])
        for choice in ask["choices"]:
            choice["label"] = local(f"{at}.choice.{choice['value']}.label", choice["label"])
    return {"provider": provider.id, "produces": list(provider.emits), **offer}


def provider(provider_id: str) -> Provider:
    try:
        return BY_ID[provider_id]
    except KeyError:
        raise LookupError(f"unknown provider '{provider_id}'") from None


def _texts(prefix: str, one: Secret | Setting) -> dict[str, str]:
    return {"label": local(f"{prefix}.label", one.label), "help": local(f"{prefix}.help", one.help)}


def listed() -> list[dict]:
    return [
        {
            "id": category.id,
            "name": local(f"category.{category.id}", category.name),
            "providers": [
                {
                    "id": item.id,
                    "name": local(f"provider.{item.id}.name", item.name),
                    "description": local(f"provider.{item.id}.description", item.description),
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
                            **_texts(f"provider.{item.id}.secret.{secret.key}", secret),
                            "multiline": secret.multiline,
                        }
                        for secret in item.secrets
                    ],
                    "settings": [
                        {
                            "key": setting.key,
                            **_texts(f"provider.{item.id}.setting.{setting.key}", setting),
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
            "description": f"By email: forward its notices to your mailbox and {extractor.entity} "
            "comes in by itself.",
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
