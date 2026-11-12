from __future__ import annotations

import base64
import os
from uuid import uuid4

import pytest

from arga_crypto import NotConfigured, Undecipherable, Vault, from_environment, hint

TOKEN = "sk-ant-oat01-sintetico-0000000000000000"


def vault(**kwargs) -> Vault:
    return Vault("hub", os.urandom(32), **kwargs)


def test_what_is_sealed_opens_again_and_the_bytes_do_not_carry_it_in_clear() -> None:
    v, ana = vault(), uuid4()

    blob = v.seal(ana, "claude_code_token", TOKEN)

    assert TOKEN.encode() not in blob
    assert v.open(ana, "claude_code_token", blob) == TOKEN


def test_two_seals_of_the_same_secret_are_different_bytes() -> None:
    v, ana = vault(), uuid4()

    assert v.seal(ana, "k", TOKEN) != v.seal(ana, "k", TOKEN)


def test_a_ciphertext_copied_to_someone_elses_row_does_not_open() -> None:
    v, ana, luis = vault(), uuid4(), uuid4()
    blob = v.seal(ana, "claude_code_token", TOKEN)

    with pytest.raises(Undecipherable):
        v.open(luis, "claude_code_token", blob)
    with pytest.raises(Undecipherable):
        v.open(ana, "otra_credencial", blob)


def test_another_module_cannot_open_it_even_with_the_same_key() -> None:
    key, ana = os.urandom(32), uuid4()
    blob = Vault("hub", key).seal(ana, "k", TOKEN)

    with pytest.raises(Undecipherable):
        Vault("caudal", key).open(ana, "k", blob)


def test_a_flipped_byte_does_not_open() -> None:
    v, ana = vault(), uuid4()
    blob = bytearray(v.seal(ana, "k", TOKEN))
    blob[-1] ^= 1

    with pytest.raises(Undecipherable):
        v.open(ana, "k", bytes(blob))


def test_rotating_the_key_keeps_opening_the_old_ones_and_marks_them_stale() -> None:
    old, ana = os.urandom(32), uuid4()
    blob = Vault("hub", old).seal(ana, "k", TOKEN)
    rotated = Vault("hub", os.urandom(32), previous=(old,))

    assert rotated.open(ana, "k", blob) == TOKEN
    assert rotated.stale(blob)
    assert not rotated.stale(rotated.seal(ana, "k", TOKEN))
    with pytest.raises(Undecipherable, match="ya no está"):
        vault().open(ana, "k", blob)


def test_the_hint_shows_only_the_last_four() -> None:
    assert hint(TOKEN) == "…0000"
    assert hint("corta") == "…"


def test_without_a_key_the_module_does_not_start(monkeypatch) -> None:
    monkeypatch.delenv("HUB_CREDENTIALS_KEY", raising=False)
    with pytest.raises(NotConfigured, match="HUB_CREDENTIALS_KEY"):
        from_environment("hub")

    monkeypatch.setenv("HUB_CREDENTIALS_KEY", "corta")
    with pytest.raises(NotConfigured, match="32 bytes"):
        from_environment("hub")


@pytest.mark.parametrize("encode", [bytes.hex, lambda k: base64.b64encode(k).decode()])
def test_the_key_can_come_as_openssl_writes_it(monkeypatch, encode) -> None:
    key = os.urandom(32)
    monkeypatch.setenv("HUB_CREDENTIALS_KEY", encode(key))

    assert from_environment("hub").key == key


def test_showing_a_vault_does_not_show_its_key() -> None:
    key = os.urandom(32)
    vault = Vault("money", key, (os.urandom(32),))

    assert key.hex() not in repr(vault) and repr(key) not in repr(vault)
    assert "money" in repr(vault)
