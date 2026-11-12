from __future__ import annotations

import hashlib
import os
from typing import Any

from arga_contracts.ai import ExtractRequest, ExtractResponse, RunRequest, RunResponse

FAKE = "fake"


def provider_name() -> str:
    return os.environ.get("OPENARGA_AI_PROVIDER", FAKE)


def _empty(schema: dict[str, Any]) -> Any:
    kind = schema.get("type")
    if kind == "object":
        return {name: _empty(sub) for name, sub in (schema.get("properties") or {}).items()}
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        return 0
    if kind == "boolean":
        return False
    if kind == "string":
        return ""
    return None


async def extract(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = ExtractRequest.model_validate(body)
    output = _empty(request.output_schema)
    return ExtractResponse(
        output=output if isinstance(output, dict) else {"value": output},
        provider=FAKE,
        model=FAKE,
    ).model_dump()


async def run(module: str, body: dict[str, Any]) -> dict[str, Any]:
    request = RunRequest.model_validate(body)
    run_id = hashlib.sha256(f"{module}:{request.key}".encode()).hexdigest()[:16]
    return RunResponse(
        status="done",
        run_id=run_id,
        summary="The fake AI provider did nothing. Configure a provider in Connections.",
        provider=FAKE,
        model=FAKE,
    ).model_dump()
