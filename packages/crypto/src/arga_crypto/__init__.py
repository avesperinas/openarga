from __future__ import annotations

import base64
import contextlib
import hashlib
import os
from dataclasses import dataclass, field
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT = 1
KEY_ID_BYTES = 4
NONCE_BYTES = 12


class NotConfigured(RuntimeError):
    pass


class Undecipherable(Exception):
    pass


def decode_key(raw: str, variable: str) -> bytes:
    raw = raw.strip()
    candidates = []
    if len(raw) == 64:
        with contextlib.suppress(ValueError):
            candidates.append(bytes.fromhex(raw))
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        with contextlib.suppress(ValueError):
            candidates.append(decoder(raw + "=" * (-len(raw) % 4)))
    for key in candidates:
        if len(key) == 32:
            return key
    raise NotConfigured(f"{variable} is not a 32-byte key in base64 or hex")


def key_id(key: bytes) -> bytes:
    return hashlib.sha256(key).digest()[:KEY_ID_BYTES]


def hint(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= 8 else "…"


@dataclass(frozen=True)
class Vault:
    module: str
    key: bytes = field(repr=False)
    previous: tuple[bytes, ...] = field(default=(), repr=False)

    def _associated(self, person: UUID, name: str) -> bytes:
        return f"arga:{self.module}:{person}:{name}".encode()

    def seal(self, person: UUID, name: str, secret: str) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        sealed = AESGCM(self.key).encrypt(nonce, secret.encode(), self._associated(person, name))
        return bytes([FORMAT]) + key_id(self.key) + nonce + sealed

    def open(self, person: UUID, name: str, blob: bytes) -> str:
        blob = bytes(blob)
        if len(blob) < 1 + KEY_ID_BYTES + NONCE_BYTES or blob[0] != FORMAT:
            raise Undecipherable("unknown format")
        wanted = blob[1 : 1 + KEY_ID_BYTES]
        nonce = blob[1 + KEY_ID_BYTES : 1 + KEY_ID_BYTES + NONCE_BYTES]
        sealed = blob[1 + KEY_ID_BYTES + NONCE_BYTES :]
        for key in (self.key, *self.previous):
            if key_id(key) != wanted:
                continue
            try:
                plain = AESGCM(key).decrypt(nonce, sealed, self._associated(person, name))
            except InvalidTag as error:
                raise Undecipherable("it does not belong to this row, or it was altered") from error
            return plain.decode()
        raise Undecipherable("encrypted with a key that is gone")

    def stale(self, blob: bytes) -> bool:
        return bytes(blob)[1 : 1 + KEY_ID_BYTES] != key_id(self.key)


def from_environment(module: str) -> Vault:
    variable = f"{module.upper()}_CREDENTIALS_KEY"
    raw = os.environ.get(variable, "").strip()
    if not raw:
        raise NotConfigured(
            f"{variable} is missing: without it no credential can be stored or used"
        )
    previous_raw = os.environ.get(f"{variable}_PREVIOUS", "").strip()
    previous = (decode_key(previous_raw, f"{variable}_PREVIOUS"),) if previous_raw else ()
    return Vault(module, decode_key(raw, variable), previous)
