from __future__ import annotations

from arga_testing.module import OTHER, PERSON, fixtures
from __MODULE_ID__ import db
from __MODULE_ID__.main import MODULE_ID, app

globals().update(fixtures(MODULE_ID, app, db))

__all__ = ["OTHER", "PERSON"]
