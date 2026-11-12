from __future__ import annotations

import os
from types import ModuleType

MODE = "CONNECTIONS_MODE"

FAKES: dict[str, ModuleType] = {}


def enabled() -> bool:
    return os.environ.get(MODE, "").strip().lower() == "fake"


def provider(name: str, real: ModuleType) -> ModuleType:
    if enabled() and name in FAKES:
        return FAKES[name]
    return real
