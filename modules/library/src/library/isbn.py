from __future__ import annotations

import re

_NOISE = re.compile(r"[\s\-]")


def _check13(first12: str) -> str:
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(first12))
    return str((10 - total % 10) % 10)


def _valid10(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{9}[0-9X]", value):
        return False
    total = sum(
        (10 - index) * (10 if char == "X" else int(char)) for index, char in enumerate(value)
    )
    return total % 11 == 0


def to_isbn13(value: str) -> str | None:
    raw = _NOISE.sub("", value).upper()
    if len(raw) == 13 and raw.isdigit() and raw[:3] in ("978", "979"):
        return raw if _check13(raw[:12]) == raw[12] else None
    if len(raw) == 10 and _valid10(raw):
        first12 = "978" + raw[:9]
        return first12 + _check13(first12)
    return None
