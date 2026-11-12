from __future__ import annotations

from pathlib import Path

from arga_testing.contract import contract
from macros.main import service

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.yaml"

globals().update(contract(service, MANIFEST))
