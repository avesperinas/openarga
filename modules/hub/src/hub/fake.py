from __future__ import annotations

import os
from types import ModuleType

import httpx

MODE = "CONNECTIONS_MODE"

FAKES: dict[str, ModuleType] = {}
UNANSWERED: list[str] = []


def enabled() -> bool:
    return os.environ.get(MODE, "").strip().lower() == "fake"


def provider(name: str, real: ModuleType) -> ModuleType:
    if enabled() and name in FAKES:
        return FAKES[name]
    return real


def handle(request: httpx.Request) -> httpx.Response:
    from hub.fakes import doubles

    answer = doubles.answer_for(request)
    if answer is None:
        UNANSWERED.append(f"{request.method} {request.url.host}{request.url.path}")
        return httpx.Response(503, json={"error": "fake mode has no double for this request"})
    return answer(request)


def transport() -> httpx.AsyncBaseTransport:
    return httpx.MockTransport(handle)
