from __future__ import annotations

import json

from travel.words import CATALOGS


def test_both_catalogs_have_the_same_keys() -> None:
    en, es = (set(json.loads((CATALOGS / f"{one}.json").read_text())) for one in ("en", "es"))

    assert en == es
