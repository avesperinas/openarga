from __future__ import annotations

import asyncio
import zlib
from collections.abc import AsyncIterator, Mapping, MutableMapping

import brotli

BROTLI_QUALITY = 5
GZIP_LEVEL = 6
MIN_SIZE = 1024
THREAD_FROM = 16 * 1024

TEXT = (
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/vnd.mapbox-vector-tile",
    "application/x-protobuf",
    "application/xml",
    "image/svg+xml",
    "text/",
)


def negotiate(accept_encoding: str | None) -> str | None:
    weights: dict[str, float] = {}
    for part in (accept_encoding or "").split(","):
        name, _, params = part.strip().partition(";")
        quality = 1.0
        key, _, value = params.strip().partition("=")
        if key.strip() == "q":
            try:
                quality = float(value)
            except ValueError:
                quality = 0.0
        if name:
            weights[name.strip().lower()] = quality
    for encoding in ("br", "gzip"):
        if weights.get(encoding, weights.get("*", 0.0)) > 0:
            return encoding
    return None


def textual(headers: Mapping[str, str]) -> bool:
    media = headers.get("content-type", "").split(";")[0].strip().lower()
    return media != "text/event-stream" and media.startswith(TEXT)


def worth(method: str, status: int, headers: Mapping[str, str]) -> bool:
    if method == "HEAD" or status < 200 or status in (204, 206, 304):
        return False
    if "content-encoding" in headers or "content-range" in headers:
        return False
    if "no-transform" in headers.get("cache-control", "").lower():
        return False
    length = headers.get("content-length")
    if length is not None and length.isdigit() and int(length) < MIN_SIZE:
        return False
    return textual(headers)


def label(headers: MutableMapping[str, str], encoding: str) -> None:
    headers["content-encoding"] = encoding
    headers.pop("accept-ranges", None)
    vary(headers)
    etag = headers.get("etag")
    if etag and not etag.startswith("W/"):
        headers["etag"] = f"W/{etag}"


def vary(headers: MutableMapping[str, str]) -> None:
    current = [part.strip() for part in headers.get("vary", "").split(",") if part.strip()]
    if "*" in current or any(part.lower() == "accept-encoding" for part in current):
        return
    headers["vary"] = ", ".join([*current, "Accept-Encoding"])


async def encoded(chunks: AsyncIterator[bytes], encoding: str) -> AsyncIterator[bytes]:
    if encoding == "br":
        compressor = brotli.Compressor(quality=BROTLI_QUALITY)

        def step(chunk: bytes) -> bytes:
            return compressor.process(chunk) + compressor.flush()

        finish = compressor.finish
    else:
        deflate = zlib.compressobj(GZIP_LEVEL, zlib.DEFLATED, 16 + zlib.MAX_WBITS)

        def step(chunk: bytes) -> bytes:
            return deflate.compress(chunk) + deflate.flush(zlib.Z_SYNC_FLUSH)

        finish = deflate.flush

    async for chunk in chunks:
        if not chunk:
            continue
        out = await asyncio.to_thread(step, chunk) if len(chunk) >= THREAD_FROM else step(chunk)
        if out:
            yield out
    yield finish()
