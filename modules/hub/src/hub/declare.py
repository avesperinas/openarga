from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

Capability = Literal["sync", "action", "lookup", "push"]

Policy = Literal["budget", "open_window", "authorized"]

Fetch = Callable[[httpx.AsyncClient, dict[str, str], Any], Awaitable[Any]]
Normalise = Callable[[str, str], str]
Clean = Callable[[dict[str, Any]], dict[str, Any]]
Search = Callable[[httpx.AsyncClient, str | None, str | None], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class Secret:
    key: str
    label: str
    help: str
    multiline: bool = False


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    help: str
    default: str = ""


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Ask:
    key: str
    kind: str
    label: str
    source: str | None = None
    depends_on: str | None = None
    optional: bool = False
    none_label: str | None = None
    default: str | None = None
    choices: tuple[Choice, ...] = ()
    defaults: tuple[str, ...] = ()
    carries: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""
    help: str = ""
    display: str | None = None


@dataclass(frozen=True)
class Offer:
    title: str
    subtitle: str
    tone: int
    asks: tuple[Ask, ...] = ()
    many: bool = False
    name: str = ""
    group: str = "other"


Recall = Callable[[Any, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Sync:
    operation: str
    fetch: Fetch
    policy: Policy | None = None
    recall: Recall | None = None


def keep(_key: str, raw: str) -> str:
    return raw


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    category: str
    description: str
    capabilities: tuple[Capability, ...]
    secrets: tuple[Secret, ...] = ()
    emits: tuple[str, ...] = ()
    lives_in: str | None = None
    available: bool = False
    schedule: str | None = None
    single: bool = False
    created_in: str | None = None
    unique_label: bool = False
    by_hand: bool = True
    authorizes: bool = False
    oauth: bool = False
    shared: tuple[str, ...] = ()
    daily_budget: int | None = None
    source: str | None = None
    internal: tuple[str, ...] = ()
    settings: tuple[Setting, ...] = ()
    sync: Sync | None = None
    normalise: Normalise = keep
    clean: Clean | None = None
    serves: tuple[str, ...] = ()
    offer: Offer | None = None
    searches: dict[str, Search] = field(default_factory=dict)

    def search_for(self, ask_key: str) -> Search | None:
        ask = (
            next((one for one in self.offer.asks if one.key == ask_key), None)
            if self.offer
            else None
        )
        if ask is None:
            return None
        return self.searches.get(ask.source or ask.key)
