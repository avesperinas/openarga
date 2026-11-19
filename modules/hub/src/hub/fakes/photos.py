from __future__ import annotations

import math
import struct
import zlib
from functools import cache
from hashlib import sha256

WIDTH, HEIGHT = 480, 320

Colour = tuple[int, int, int]
PALETTES: tuple[tuple[Colour, Colour, Colour, Colour, Colour], ...] = (
    ((120, 170, 220), (250, 214, 165), (110, 140, 100), (60, 95, 70), (255, 236, 200)),
    ((70, 110, 170), (240, 160, 120), (130, 100, 120), (70, 60, 90), (255, 220, 180)),
    ((150, 200, 230), (225, 240, 245), (90, 150, 170), (40, 100, 120), (255, 250, 230)),
    ((200, 180, 150), (250, 230, 190), (170, 130, 90), (120, 85, 60), (255, 240, 210)),
    ((110, 150, 190), (200, 220, 230), (100, 120, 140), (55, 75, 95), (245, 245, 250)),
)


def mix(a: Colour, b: Colour, share: float) -> Colour:
    return (
        round(a[0] + (b[0] - a[0]) * share),
        round(a[1] + (b[1] - a[1]) * share),
        round(a[2] + (b[2] - a[2]) * share),
    )


@cache
def landscape(name: str) -> bytes:
    seed = sha256(name.encode()).digest()
    sky, horizon, far, near, sun = PALETTES[seed[0] % len(PALETTES)]
    sun_x, sun_y, sun_r = (
        WIDTH * (0.2 + seed[1] / 400),
        HEIGHT * (0.18 + seed[2] / 1200),
        22 + seed[3] % 14,
    )
    phase_far, phase_near = seed[4] / 40, seed[5] / 40
    rows = []
    for y in range(HEIGHT):
        row = bytearray([0])
        sky_colour = mix(sky, horizon, min(1.0, y / (HEIGHT * 0.62)))
        for x in range(WIDTH):
            far_line = (
                HEIGHT * 0.55
                + 22 * math.sin(x / 70 + phase_far)
                + 10 * math.sin(x / 23 + phase_near)
            )
            near_line = (
                HEIGHT * 0.72
                + 18 * math.sin(x / 95 + phase_near)
                + 6 * math.sin(x / 31 + phase_far)
            )
            if y > near_line:
                colour = mix(near, (20, 30, 25), min(1.0, (y - near_line) / HEIGHT))
            elif y > far_line:
                colour = mix(far, horizon, 0.25)
            elif math.hypot(x - sun_x, y - sun_y) < sun_r:
                colour = sun
            else:
                colour = sky_colour
            row.extend(colour)
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
