from __future__ import annotations

import asyncio
import gzip
import os
import struct
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from hub.declare import Provider
from hub.providers import USER_AGENT

BUILDS = "https://build-metadata.protomaps.dev/builds.json"
BUILD = "https://build.protomaps.com/{key}"

BUILD_SECONDS = 24 * 3600
LEAVES = 64
TILES = 512
MAX_ZOOM = 15
HEADER_BYTES = 16_384
RETRY_SECONDS = 60


def timeout() -> float:
    return float(os.environ.get("MAPS_SOURCE_TIMEOUT_SECONDS", "15"))


class SourceFailed(Exception):
    pass


@dataclass(frozen=True)
class Entry:
    tile_id: int
    offset: int
    length: int
    run_length: int


@dataclass(frozen=True)
class Header:
    root_offset: int
    root_length: int
    leaf_offset: int
    tile_offset: int
    internal_compression: int
    tile_compression: int
    max_zoom: int


def tile_id(z: int, x: int, y: int) -> int:
    before = ((1 << (2 * z)) - 1) // 3
    n = 1 << z
    d = 0
    tx, ty = x, y
    s = n >> 1
    while s > 0:
        rx = 1 if tx & s else 0
        ry = 1 if ty & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                tx, ty = n - 1 - tx, n - 1 - ty
            tx, ty = ty, tx
        s >>= 1
    return before + d


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, at
        shift += 7


def header(data: bytes) -> Header:
    if data[:7] != b"PMTiles" or data[7] != 3:
        raise SourceFailed("not a PMTiles v3 file")
    fields = struct.unpack_from("<11Q", data, 8)
    return Header(
        root_offset=fields[0],
        root_length=fields[1],
        leaf_offset=fields[4],
        tile_offset=fields[6],
        internal_compression=data[97],
        tile_compression=data[98],
        max_zoom=data[101],
    )


def _inflate(data: bytes, compression: int) -> bytes:
    if compression in (0, 1):
        return data
    if compression == 2:
        return gzip.decompress(data)
    raise SourceFailed(f"compression {compression} not supported")


def directory(data: bytes) -> list[Entry]:
    count, at = _varint(data, 0)
    ids, runs, lengths, offsets = [], [], [], []
    last = 0
    for _ in range(count):
        delta, at = _varint(data, at)
        last += delta
        ids.append(last)
    for _ in range(count):
        value, at = _varint(data, at)
        runs.append(value)
    for _ in range(count):
        value, at = _varint(data, at)
        lengths.append(value)
    for index in range(count):
        value, at = _varint(data, at)
        if value == 0 and index > 0:
            offsets.append(offsets[index - 1] + lengths[index - 1])
        else:
            offsets.append(value - 1)
    return [Entry(*one) for one in zip(ids, offsets, lengths, runs, strict=True)]


def find(entries: list[Entry], wanted: int) -> Entry | None:
    low, high = 0, len(entries) - 1
    while low <= high:
        middle = (low + high) >> 1
        if entries[middle].tile_id < wanted:
            low = middle + 1
        elif entries[middle].tile_id > wanted:
            high = middle - 1
        else:
            return entries[middle]
    if high >= 0:
        entry = entries[high]
        if entry.run_length == 0 or wanted - entry.tile_id < entry.run_length:
            return entry
    return None


class _Archive:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.key: str | None = None
        self.chosen_at = 0.0
        self.head: Header | None = None
        self.root: list[Entry] = []
        self.leaves: OrderedDict[int, list[Entry]] = OrderedDict()
        self.tiles: OrderedDict[tuple[int, int, int], bytes | None] = OrderedDict()
        self.refused: tuple[float, str] | None = None

    def forget(self) -> None:
        self.key = None
        self.head = None
        self.root = []
        self.leaves.clear()
        self.tiles.clear()


ARCHIVE = _Archive()


async def _range(client: httpx.AsyncClient, url: str, offset: int, length: int) -> bytes:
    try:
        response = await client.get(
            url,
            headers={"range": f"bytes={offset}-{offset + length - 1}", "user-agent": USER_AGENT},
            timeout=timeout(),
        )
    except httpx.HTTPError as error:
        raise SourceFailed(f"Protomaps did not answer: {type(error).__name__}") from error
    if response.status_code == 404:
        ARCHIVE.forget()
        raise SourceFailed("that map version is gone; another will be chosen")
    if response.status_code not in (200, 206):
        raise SourceFailed(f"Protomaps answered {response.status_code}")
    return response.content[:length] if response.status_code == 200 else response.content


async def _latest(client: httpx.AsyncClient) -> str:
    if ARCHIVE.refused is not None and time.monotonic() - ARCHIVE.refused[0] < RETRY_SECONDS:
        raise SourceFailed(ARCHIVE.refused[1])
    try:
        response = await client.get(BUILDS, headers={"user-agent": USER_AGENT}, timeout=timeout())
        response.raise_for_status()
        key = response.json()[-1]["key"]
    except httpx.HTTPStatusError as error:
        why = f"answered {error.response.status_code}"
    except httpx.HTTPError as error:
        why = f"did not answer ({type(error).__name__})"
    except ValueError:
        why = "its answer is not JSON"
    except (KeyError, IndexError, TypeError):
        why = "its map list does not have the usual shape"
    else:
        ARCHIVE.refused = None
        return key
    reason = f"Protomaps did not say which map is the latest: {why}"
    ARCHIVE.refused = (time.monotonic(), reason)
    raise SourceFailed(reason)


async def _open(client: httpx.AsyncClient) -> str:
    if ARCHIVE.key is None or time.monotonic() - ARCHIVE.chosen_at > BUILD_SECONDS:
        try:
            key = await _latest(client)
        except SourceFailed:
            if ARCHIVE.key is None:
                raise
            ARCHIVE.chosen_at = time.monotonic() - BUILD_SECONDS + RETRY_SECONDS
        else:
            if key != ARCHIVE.key:
                ARCHIVE.forget()
                ARCHIVE.key = key
            ARCHIVE.chosen_at = time.monotonic()
    url = BUILD.format(key=ARCHIVE.key)
    if ARCHIVE.head is None:
        start = await _range(client, url, 0, HEADER_BYTES)
        head = header(start)
        root = start[head.root_offset : head.root_offset + head.root_length]
        if len(root) < head.root_length:
            root = await _range(client, url, head.root_offset, head.root_length)
        ARCHIVE.root = directory(_inflate(root, head.internal_compression))
        ARCHIVE.head = head
    return url


async def tile(client: httpx.AsyncClient, z: int, x: int, y: int) -> bytes | None:
    key = (z, x, y)
    if key in ARCHIVE.tiles:
        ARCHIVE.tiles.move_to_end(key)
        return ARCHIVE.tiles[key]
    async with ARCHIVE.lock:
        url = await _open(client)
    head = ARCHIVE.head
    assert head is not None
    wanted = tile_id(z, x, y)
    entries = ARCHIVE.root
    found: bytes | None = None
    for _ in range(4):
        entry = find(entries, wanted)
        if entry is None:
            break
        if entry.run_length > 0:
            raw = await _range(client, url, head.tile_offset + entry.offset, entry.length)
            found = _inflate(raw, head.tile_compression)
            break
        leaf = ARCHIVE.leaves.get(entry.offset)
        if leaf is None:
            raw = await _range(client, url, head.leaf_offset + entry.offset, entry.length)
            leaf = directory(_inflate(raw, head.internal_compression))
            ARCHIVE.leaves[entry.offset] = leaf
            if len(ARCHIVE.leaves) > LEAVES:
                ARCHIVE.leaves.popitem(last=False)
        entries = leaf
    ARCHIVE.tiles[key] = found
    if len(ARCHIVE.tiles) > TILES:
        ARCHIVE.tiles.popitem(last=False)
    return found


async def check(client: httpx.AsyncClient) -> None:
    key = await _latest(client)
    header(await _range(client, BUILD.format(key=key), 0, 127))


def build() -> str | None:
    return ARCHIVE.key


SOURCES = (
    Provider(
        id="protomaps",
        name="Protomaps",
        category="places",
        description="The streets of anywhere in the world, from OpenStreetMap, "
        "for the map of each day of a trip in Travel. No key: it "
        "connects by itself the first time it is asked.",
        capabilities=("lookup",),
        serves=("maps.tile",),
        available=True,
        single=True,
    ),
)
