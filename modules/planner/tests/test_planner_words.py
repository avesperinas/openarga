from __future__ import annotations

from arga_module.i18n import missing
from planner.words import CATALOGS


def test_both_catalogs_have_the_same_keys() -> None:
    assert missing(CATALOGS) == []
