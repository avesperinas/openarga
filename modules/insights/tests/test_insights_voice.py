from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from insights_taste_world import pill

from arga_tenancy import as_user
from insights import craft, passes, voice
from insights.main import MADRID, as_role

WRITE = {"x-arga-scopes": "insights:read insights:write"}
STRANGER = UUID("00000000-0000-4000-8000-00000000c0c0")
RATE = 16000


def fake(language: str = "es", fail: bool = False) -> voice.Speaker:

    def say(sentence: str) -> bytes:
        if fail:
            raise RuntimeError("sin voz")
        return b"\x10\x00" * (RATE // 2)

    return voice.Speaker(name=f"prueba-{language}", rate=RATE, say=say)


def test_it_says_what_the_app_highlights_in_the_same_order() -> None:
    found = SimpleNamespace(
        headline="Titular",
        lead="Entradilla",
        sections=[{"title": "Ladillo", "text": "Uno.\n\nDos.\nTres."}],
        to_tell="Dato.",
        to_think="¿Y?",
    )

    parts, headings = voice.spoken_parts(found)

    assert parts == [
        "Titular",
        "Entradilla",
        "Ladillo",
        "Uno.",
        "Dos.",
        "Tres.",
        "Para contar. Dato.",
        "Para pensar: ¿Y?",
    ]
    assert headings == {0, 2}


def test_the_timeline_says_when_each_part_starts_with_a_longer_pause_after_a_heading() -> None:
    pcm, timeline = voice.render(["Titular", "Entradilla", "", "Final"], {0}, fake())

    assert timeline == [0.0, 1.35, 2.4, 2.4]
    assert len(pcm) / 2 / RATE == pytest.approx(3.45, abs=0.01)


def test_the_audio_is_a_small_mono_mp3() -> None:
    found = SimpleNamespace(
        headline="Titular", lead="Entradilla", sections=[], to_tell="Dato.", to_think=None
    )

    spoken = voice.speak(found, fake())

    assert spoken.content[:3] == b"ID3" or spoken.content[0] == 0xFF
    assert spoken.duration == pytest.approx(3.45, abs=0.01)
    assert len(spoken.timeline) == 3


def test_without_the_voice_on_disk_there_is_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(voice, "VOICES_DIR", tmp_path)
    voice.speaker.cache_clear()

    assert voice.speaker("es") is None
    assert voice.speaker("fr") is None
    voice.speaker.cache_clear()


@pytest.fixture
def hub(monkeypatch) -> None:

    def answer(request: httpx.Request) -> httpx.Response:
        json.loads(request.content)
        return httpx.Response(200, json={"outcome": "queued", "run": "r", "repeated": False})

    monkeypatch.setattr(passes, "transport", lambda: httpx.MockTransport(answer))


async def publish(api, key: str, **overrides) -> str:
    async with as_role("mod_insights") as connection:
        await craft.run(connection, "pill", key, datetime.now(MADRID), random.Random(1))
    response = await api.post("/tools/publish_pill", json=pill(key, **overrides), headers=WRITE)
    assert response.status_code == 200, response.text
    content = response.json()["content"]
    assert content["published"], content
    return content["published"]["pill_id"]


async def test_a_new_pill_gets_its_voice_and_the_app_learns_its_timeline(api, hub) -> None:
    pill_id = await publish(api, "pill:2026-11-10")
    assert (await api.get(f"/pills/{pill_id}")).json()["pill"]["audio"] is None

    done = await voice.generate(lambda: as_role("mod_insights"), voice_for=lambda _: fake())
    again = await voice.generate(lambda: as_role("mod_insights"), voice_for=lambda _: fake())

    assert (done, again) == (1, 0)
    audio = (await api.get(f"/pills/{pill_id}")).json()["pill"]["audio"]
    assert len(audio["timeline"]) == 2 + 3 * 5 + 2
    assert audio["timeline"][0] == 0
    assert audio["duration"] > audio["timeline"][-1]
    today = (await api.get("/today")).json()
    assert today["pill"] is None or today["pill"]["id"] != pill_id or today["pill"]["audio"]


async def test_one_that_cannot_be_said_does_not_stop_the_rest(api, hub) -> None:
    voice.FAILED.clear()
    german = await publish(api, "pill:2026-11-09", language="de")
    spanish = await publish(api, "pill:2026-11-08", topic="La batalla de Mantinea")

    done = await voice.generate(
        lambda: as_role("mod_insights"),
        voice_for=lambda language: fake(language, fail=language == "de"),
    )
    retried = await voice.generate(lambda: as_role("mod_insights"), voice_for=lambda _: fake())

    assert done == 1
    assert retried == 0
    assert (await api.get(f"/pills/{german}")).json()["pill"]["audio"] is None
    assert (await api.get(f"/pills/{spanish}")).json()["pill"]["audio"] is not None
    voice.FAILED.clear()


async def test_an_old_pill_or_one_without_voice_in_its_language_waits(api, hub) -> None:
    await publish(api, "pill:2026-11-10", language="fr")
    later = datetime(2026, 12, 1, tzinfo=UTC)

    assert await voice.generate(lambda: as_role("mod_insights"), voice_for=lambda _: fake()) == 0
    await publish(api, "pill:2026-11-11", topic="La batalla de Mantinea")
    assert await voice.generate(lambda: as_role("mod_insights"), later, lambda _: fake()) == 0


async def test_the_audio_is_served_whole_or_in_pieces_and_only_to_its_owner(api, hub) -> None:
    pill_id = await publish(api, "pill:2026-11-10")
    await voice.generate(lambda: as_role("mod_insights"), voice_for=lambda _: fake())

    whole = await api.get(f"/pills/{pill_id}/audio")
    size = len(whole.content)
    first = await api.get(f"/pills/{pill_id}/audio", headers={"range": "bytes=0-1"})
    tail = await api.get(f"/pills/{pill_id}/audio", headers={"range": "bytes=-100"})
    rest = await api.get(f"/pills/{pill_id}/audio", headers={"range": "bytes=100-"})
    beyond = await api.get(f"/pills/{pill_id}/audio", headers={"range": f"bytes={size}-"})
    head = await api.head(f"/pills/{pill_id}/audio")
    with as_user(STRANGER, ()):
        stranger = await api.get(f"/pills/{pill_id}/audio")
    missing = await api.get("/pills/00000000-0000-4000-8000-000000000000/audio")

    assert whole.status_code == 200
    assert whole.headers["content-type"] == "audio/mpeg"
    assert whole.headers["accept-ranges"] == "bytes"
    assert first.status_code == 206
    assert first.content == whole.content[:2]
    assert first.headers["content-range"] == f"bytes 0-1/{size}"
    assert tail.content == whole.content[-100:]
    assert rest.content == whole.content[100:]
    assert beyond.status_code == 416
    assert beyond.headers["content-range"] == f"bytes */{size}"
    assert head.status_code == 200
    assert stranger.status_code == 404
    assert missing.status_code == 404


def test_the_image_brings_a_voice_for_each_language_insights_speaks() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "voices", Path(__file__).resolve().parents[1] / "voices.py"
    )
    assert spec and spec.loader
    pinned = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pinned)

    assert set(pinned.VOICES) == set(voice.VOICES.values())
    assert set(voice.SMOKE) == set(voice.VOICES)
