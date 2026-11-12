from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from notebook import markdown as md


@dataclass(frozen=True)
class Ficha:
    app: str
    app_name: str
    record_id: str
    title: str
    kind: str
    href: str
    day: date | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def target(self) -> str:
        return f"{self.app}:{self.record_id}"


def link_key(app: str, record_id: str) -> str:
    return md.key(f"{app}:{record_id}")


def properties(one: Ficha) -> dict[str, Any]:
    return {"arga": one.target, "tipo": one.kind, **one.properties}


def day_properties(fichas: list[Ficha]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for one in sorted(fichas, key=_order):
        for name, value in one.properties.items():
            found.setdefault(name, value)
    return found


def _order(one: Ficha) -> tuple[str, str, str]:
    return (md.key(one.app_name), md.key(one.title), one.record_id)


def day_block(fichas: list[Ficha]) -> str:
    sections: list[str] = []
    current: str | None = None
    parts: list[str] = []
    for one in sorted(fichas, key=_order):
        if one.app_name != current:
            if current is not None:
                sections.append(_section(current, parts))
            current, parts = one.app_name, []
        if one.body.strip():
            parts.append(one.body.strip("\n"))
    if current is not None:
        sections.append(_section(current, parts))
    return "\n\n".join(section for section in sections if section)


def _section(name: str, parts: list[str]) -> str:
    if not parts:
        return ""
    return f"### {name}\n\n" + "\n\n".join(parts)


@dataclass(frozen=True)
class Owned:
    block: str
    properties: dict[str, Any]
    at_end: bool
    apps: list[Ficha]

    @property
    def names(self) -> str:
        found: list[str] = []
        for one in self.apps:
            if one.app_name not in found:
                found.append(one.app_name)
        return " y ".join(found) if len(found) < 3 else ", ".join(found[:-1]) + " y " + found[-1]


def owned(fichas: list[Ficha]) -> Owned | None:
    if not fichas:
        return None
    days = [one for one in fichas if one.day is not None]
    if days:
        return Owned(day_block(days), day_properties(days), True, sorted(days, key=_order))
    one = fichas[0]
    return Owned(one.body.strip("\n"), properties(one), False, [one])


def compose(content: str, wanted: Owned | None, before: dict[str, Any] | None = None) -> str:
    keep = wanted.properties if wanted else {}
    drop = [name for name in (before or {}) if name not in keep]
    current = md.properties(content)
    changes = {name: value for name, value in keep.items() if current.get(name, _MISSING) != value}
    gone = [name for name in drop if name in current]
    if changes or gone:
        with contextlib.suppress(md.InvalidProperties):
            content = md.set_properties(content, changes, gone)
    if wanted is None:
        return md.with_block(content, None)
    return md.with_block(content, wanted.block, at_end=wanted.at_end)


_MISSING = object()
