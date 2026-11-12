from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

CONTACT_URL = os.environ.get("OPENARGA_CONTACT_URL", "https://github.com/avesperinas/openarga")
USER_AGENT = f"OpenArga/0.1 (+{CONTACT_URL})"


class SourceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        rate_limited: bool = False,
        code: str | None = None,
    ):
        super().__init__(message)
        self.transient = transient
        self.rate_limited = rate_limited
        self.code = code


@dataclass
class Fetched:
    events: list[dict[str, Any]] = field(default_factory=list)
    problem: str | None = None
    rate_limited: bool = False
    note: str | None = None
    config: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
