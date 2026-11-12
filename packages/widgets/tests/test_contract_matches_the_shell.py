from __future__ import annotations

import re
from pathlib import Path

from arga_widgets import BODIES, REQUIRED

ROOT = Path(__file__).resolve().parents[3]
SHELL = ROOT / "shell" / "app" / "lib" / "kernel.ts"
CARD = ROOT / "shell" / "app" / "components" / "WidgetCard.tsx"


def shell_kinds() -> set[str]:
    source = SHELL.read_text(encoding="utf-8")
    union = source.split("export type WidgetKind =")[1].split(";")[0]
    return set(re.findall(r'"([a-z-]+)"', union))


def shell_fields() -> set[str]:
    source = SHELL.read_text(encoding="utf-8")
    body = source.split("export interface EnvelopeBody {")[1].split("\n}")[0]
    return set(re.findall(r"^\s{2}(\w+)\??:", body, re.MULTILINE))


def test_the_same_kinds_on_both_sides() -> None:
    assert set(BODIES) == shell_kinds()
    assert set(REQUIRED) == shell_kinds()


def test_no_field_exists_on_only_one_side() -> None:
    mine = {name for model in BODIES.values() for name in model.model_fields}
    assert mine == shell_fields()


def test_every_kind_is_painted_by_the_shell() -> None:
    painted = set(re.findall(r'case "([a-z-]+)":', CARD.read_text(encoding="utf-8")))
    assert set(BODIES) - painted == set()


def test_a_row_has_the_same_fields_on_both_sides() -> None:
    from arga_widgets import Row

    source = SHELL.read_text(encoding="utf-8")
    row = source.split("rows?: {")[1].split("}[]")[0]
    assert set(Row.model_fields) == set(re.findall(r"(\w+)\??:", row))
