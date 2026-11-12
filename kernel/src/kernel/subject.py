from __future__ import annotations

from fastapi import HTTPException

SUBJECT_HEADER = "x-arga-subject"


def subject_of(header: str | None) -> str:
    if not header:
        raise HTTPException(
            status_code=401,
            detail=f"missing {SUBJECT_HEADER}; the gateway injects it after verifying who you are",
        )
    return header
