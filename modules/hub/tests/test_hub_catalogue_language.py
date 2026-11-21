from __future__ import annotations

import json
from pathlib import Path

from hub import catalogue

SPANISH = json.loads(
    (Path(catalogue.__file__).parent / "providers" / "i18n" / "es.json").read_text(encoding="utf-8")
)


def test_every_category_and_group_has_a_spanish_name() -> None:
    missing = [
        f"category.{one.id}" for one in catalogue.CATEGORIES if f"category.{one.id}" not in SPANISH
    ]
    missing += [f"group.{one.id}" for one in catalogue.GROUPS if f"group.{one.id}" not in SPANISH]
    assert missing == []
