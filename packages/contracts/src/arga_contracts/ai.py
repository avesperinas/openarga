from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["fast", "smart"]

EXTRACT = "ai.extract"
RUN = "ai.run"


class ExtractRequest(BaseModel):
    role: Role = "fast"
    instructions: str = Field(min_length=1, max_length=8000)
    input: str = Field(min_length=1, max_length=200_000)
    output_schema: dict[str, Any]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ExtractResponse(BaseModel):
    output: dict[str, Any]
    provider: str
    model: str
    usage: Usage = Usage()


class RunRequest(BaseModel):
    role: Role = "smart"
    task: str = Field(min_length=1, max_length=20_000)
    key: str = Field(min_length=1, max_length=120)
    web: bool = False
    max_steps: int = Field(default=30, ge=1, le=100)


class RunResponse(BaseModel):
    status: Literal["queued", "done", "failed", "repeated"]
    run_id: str | None = None
    summary: str | None = None
    provider: str | None = None
    model: str | None = None
