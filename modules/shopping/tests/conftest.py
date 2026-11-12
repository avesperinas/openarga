from __future__ import annotations

from pathlib import Path

from arga_testing.module import OTHER, PERSON, fixtures
from shopping import db
from shopping.main import MODULE_ID, app

SCHEMA = db.SCHEMA
MODULES = Path(__file__).resolve().parents[2]

globals().update(fixtures(MODULE_ID, app, db))

__all__ = ["OTHER", "PERSON"]
