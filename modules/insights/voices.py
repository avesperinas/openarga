from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/cf910fb59f1d79ab3b625a63993a108751c6c25d"
)

VOICES = {
    "es_ES-davefx-medium": (
        "es/es_ES/davefx/medium",
        "d2c9224e122321aac3c33343957fff4d0f465226cb74c66b0f520ca3f8c0dd07",
        "531c4051502e1acbc10b42437f11679bfce9e3919e1796e51fabd73e01e7fd2e",
    ),
    "de_DE-thorsten-medium": (
        "de/de_DE/thorsten/medium",
        "fd270eb3d1ebf91d763f8a0f949b1b1bebdfefaea18c3aaf8577dd34536e064f",
        "cf245c91668e74cb6716f38647ae3d6d9bac42965872596f65f9ab2b7d7221ed",
    ),
    "en_GB-alba-medium": (
        "en/en_GB/alba/medium",
        "1f9da809b6da1ef4190bb5dd6cce4f4af803274539e9cf9e0693085150bac3d7",
        "6214603a0dd60e9dcd05502e23ef07fbe3d9af36d3189c8cc3eb129e1a099d6f",
    ),
}


def fetch(url: str, target: Path, sha256: str) -> None:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as out:  # noqa: S310 - URL fija de arriba
        while block := response.read(1 << 20):
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != sha256:
        target.unlink()
        raise SystemExit(f"{target.name}: sha256 {digest.hexdigest()} y se esperaba {sha256}")


def main(argv: list[str]) -> int:
    folder = Path(argv[1] if len(argv) > 1 else "/opt/voices")
    folder.mkdir(parents=True, exist_ok=True)
    for name, (path, model, config) in VOICES.items():
        fetch(f"{BASE}/{path}/{name}.onnx", folder / f"{name}.onnx", model)
        fetch(f"{BASE}/{path}/{name}.onnx.json", folder / f"{name}.onnx.json", config)
        print(f"voz · {name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
