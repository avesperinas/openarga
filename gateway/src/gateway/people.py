from __future__ import annotations

import re
import time
from dataclasses import dataclass
from uuid import UUID

import httpx

from gateway.flight import Flight

USER_HEADER = "x-arga-user"
SPACES_HEADER = "x-arga-spaces"
TTL_SECONDS = 300
PREFERENCE_HEADERS = {
    "locale": "x-arga-locale",
    "timezone": "x-arga-timezone",
    "currency": "x-arga-currency",
    "country": "x-arga-country",
    "region": "x-arga-region",
    "area": "x-arga-area",
}
HEADER_SAFE = re.compile(r"^[A-Za-z0-9_+/-]{1,64}$")


@dataclass(frozen=True)
class Person:
    id: str
    spaces: tuple[str, ...] = ()
    preferences: tuple[tuple[str, str], ...] = ()

    def headers(self) -> list[tuple[bytes, bytes]]:
        found = [(USER_HEADER.encode(), self.id.encode())]
        if self.spaces:
            found.append((SPACES_HEADER.encode(), ",".join(self.spaces).encode()))
        found.extend((name.encode(), value.encode()) for name, value in self.preferences)
        return found


def preferences_of(body: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(body, dict):
        return ()
    return tuple(
        (header, value)
        for field, header in PREFERENCE_HEADERS.items()
        if isinstance(value := body.get(field), str) and HEADER_SAFE.match(value)
    )


class People:
    def __init__(self, client: httpx.AsyncClient, kernel_url: str) -> None:
        self.client = client
        self.kernel_url = kernel_url
        self._known: dict[str, tuple[float, Person]] = {}
        self._flight = Flight()

    async def person_for(self, subject: str) -> Person | None:
        cached = self._known.get(subject)
        if cached is not None and time.monotonic() - cached[0] < TTL_SECONDS:
            return cached[1]
        return await self._flight.run(subject, lambda: self._ask(subject))

    async def _ask(self, subject: str) -> Person | None:
        try:
            response = await self.client.post(
                f"{self.kernel_url}/internal/users", json={"subject": subject}, timeout=5.0
            )
            response.raise_for_status()
            body = response.json()
            person = Person(
                id=str(UUID(body["id"])),
                spaces=tuple(str(UUID(space)) for space in body.get("spaces") or ()),
                preferences=preferences_of(body.get("preferences")),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return None
        self._known[subject] = (time.monotonic(), person)
        return person

    def forget(self, subject: str) -> None:
        self._known.pop(subject, None)

    async def id_for(self, subject: str) -> str | None:
        person = await self.person_for(subject)
        return person.id if person is not None else None
