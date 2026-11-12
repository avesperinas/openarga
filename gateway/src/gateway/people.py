from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

import httpx

from gateway.flight import Flight

USER_HEADER = "x-arga-user"
SPACES_HEADER = "x-arga-spaces"
TTL_SECONDS = 300


@dataclass(frozen=True)
class Person:
    id: str
    spaces: tuple[str, ...] = ()

    def headers(self) -> list[tuple[bytes, bytes]]:
        found = [(USER_HEADER.encode(), self.id.encode())]
        if self.spaces:
            found.append((SPACES_HEADER.encode(), ",".join(self.spaces).encode()))
        return found


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
