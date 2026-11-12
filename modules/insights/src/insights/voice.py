from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

VOICES = {
    "es": "es_ES-davefx-medium",
    "de": "de_DE-thorsten-medium",
    "en": "en_GB-alba-medium",
}
VOICES_DIR = Path(os.environ.get("INSIGHTS_VOICES_DIR", "/opt/voices"))
PAUSE = 0.55
PAUSE_HEADING = 0.85
BITRATE = 48
RECENT = timedelta(days=3)
MEDIA_TYPE = "audio/mpeg"
FAILED: set[str] = set()


class PillAudio(BaseModel):
    duration: float
    timeline: list[float]


@dataclass(frozen=True)
class Spoken:
    content: bytes
    duration: float
    timeline: list[float]


@dataclass(frozen=True)
class Speaker:
    name: str
    rate: int
    say: Callable[[str], bytes]


def paragraphs(body: str) -> list[str]:
    return [one.strip() for one in re.split(r"\n\s*\n|\n", body) if one.strip()]


def spoken_parts(pill: Any) -> tuple[list[str], set[int]]:
    parts: list[str] = [pill.headline, pill.lead]
    headings = {0}
    for section in pill.sections:
        headings.add(len(parts))
        parts.append(str(section.get("title", "")))
        parts.extend(paragraphs(str(section.get("text", ""))))
    parts.append(f"Para contar. {pill.to_tell}")
    if pill.to_think:
        parts.append(f"Para pensar: {pill.to_think}")
    return parts, headings


def silence(seconds: float, rate: int) -> bytes:
    return b"\x00\x00" * int(seconds * rate)


def render(parts: list[str], headings: set[int], speaker: Speaker) -> tuple[bytes, list[float]]:
    pcm = bytearray()
    timeline: list[float] = []
    for index, part in enumerate(parts):
        timeline.append(round(len(pcm) / 2 / speaker.rate, 2))
        clean = " ".join(part.split())
        if not clean:
            continue
        pcm += speaker.say(clean)
        pcm += silence(PAUSE_HEADING if index in headings else PAUSE, speaker.rate)
    return bytes(pcm), timeline


def mp3(pcm: bytes, rate: int) -> bytes:
    import lameenc  # noqa: PLC0415 - solo el worker la carga

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(BITRATE)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm) + encoder.flush())


def speak(pill: Any, speaker: Speaker) -> Spoken:
    parts, headings = spoken_parts(pill)
    pcm, timeline = render(parts, headings, speaker)
    return Spoken(
        content=mp3(pcm, speaker.rate),
        duration=round(len(pcm) / 2 / speaker.rate, 2),
        timeline=timeline,
    )


@cache
def speaker(language: str) -> Speaker | None:
    name = VOICES.get(language)
    if name is None:
        return None
    model = VOICES_DIR / f"{name}.onnx"
    if not model.exists() or not model.with_suffix(".onnx.json").exists():
        return None
    from piper import PiperVoice  # noqa: PLC0415 - solo el worker la carga

    loaded = PiperVoice.load(str(model))

    def say(sentence: str) -> bytes:
        return b"".join(chunk.audio_int16_bytes for chunk in loaded.synthesize(sentence))

    return Speaker(name=name, rate=loaded.config.sample_rate, say=say)


async def waiting(connection: AsyncConnection, now: datetime, limit: int = 3) -> list[Any]:
    from insights import pills  # noqa: PLC0415 - pills importa este módulo

    rows = await connection.execute(
        text(f"""
            select {pills.PILL_COLUMNS} from insights.insights_pill
            where created_at >= :since and language = any(:languages)
              and not exists (
                select 1 from insights.insights_pill_audio a where a.pill_id = insights_pill.id
              )
            order by created_at desc limit :limit
        """),
        {"since": now - RECENT, "languages": list(VOICES), "limit": limit},
    )
    return [pills.Pill.model_validate(dict(row._mapping)) for row in rows]


async def store(connection: AsyncConnection, pill_id: str, spoken: Spoken, voice: str) -> None:
    await connection.execute(
        text("""
            insert into insights.insights_pill_audio (pill_id, content, type, duration, timeline, voice)
            values (cast(:pill as uuid), :content, :type, :duration, cast(:timeline as jsonb),
                    :voice)
            on conflict (pill_id) do nothing
        """),
        {
            "pill": pill_id,
            "content": spoken.content,
            "type": MEDIA_TYPE,
            "duration": spoken.duration,
            "timeline": _json(spoken.timeline),
            "voice": voice,
        },
    )


def _json(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{value:g}" for value in values) + "]"


class NoAudio(LookupError):
    pass


async def content(connection: AsyncConnection, pill_id: str) -> tuple[bytes, str]:
    row = (
        await connection.execute(
            text(
                "select content, type from insights.insights_pill_audio where pill_id = cast(:id as uuid)"
            ),
            {"id": pill_id},
        )
    ).first()
    if row is None:
        raise NoAudio(pill_id)
    return bytes(row.content), row.type


async def generate(
    connection_for: Callable[[], Any],
    now: datetime | None = None,
    voice_for: Callable[[str], Speaker | None] = speaker,
    limit: int = 3,
) -> int:
    import asyncio  # noqa: PLC0415

    now = now or datetime.now(UTC)
    async with connection_for() as connection:
        found = await waiting(connection, now, limit)
    done = 0
    for pill in found:
        voice = voice_for(pill.language)
        if voice is None or pill.id in FAILED:
            continue
        try:
            spoken = await asyncio.to_thread(speak, pill, voice)
        except Exception as error:  # noqa: BLE001 - una píldora que no suena no para las demás
            FAILED.add(pill.id)
            print(f"worker · voz · {pill.id}: {type(error).__name__}: {error}", file=sys.stderr)
            continue
        async with connection_for() as connection:
            await store(connection, pill.id, spoken, voice.name)
        done += 1
    return done


SMOKE = {
    "es": "En Leuctra, un ejército tebano cambió la guerra.",
    "de": "Bei Leuktra veränderte ein thebanisches Heer den Krieg.",
    "en": "At Leuctra, a Theban army changed the art of war.",
}


def smoke() -> int:
    for language in VOICES:
        found = speaker(language)
        if found is None:
            print(f"voz · {language}: no está en {VOICES_DIR}", file=sys.stderr)
            return 1
        pcm, _ = render([SMOKE[language]], set(), found)
        seconds = len(pcm) / 2 / found.rate
        encoded = mp3(pcm, found.rate)
        if seconds < 1 or len(encoded) < 4000:
            print(f"voz · {language}: {seconds:.1f} s, {len(encoded)} bytes", file=sys.stderr)
            return 1
        print(f"voz · {found.name}: {seconds:.1f} s, {len(encoded)} bytes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(smoke())
