from __future__ import annotations

import httpx

from arga_tenancy import kernel_url, user_headers


class Unavailable(Exception):
    pass


def transport() -> httpx.AsyncBaseTransport | None:
    return None


async def of_caller() -> list[dict]:
    try:
        async with httpx.AsyncClient(transport=transport()) as client:
            response = await client.get(
                f"{kernel_url()}/internal/spaces", headers=user_headers(), timeout=10.0
            )
    except httpx.HTTPError as error:
        raise Unavailable("the kernel is not answering") from error
    if response.status_code != 200:
        raise Unavailable(f"el kernel contesta {response.status_code}")
    return response.json()
