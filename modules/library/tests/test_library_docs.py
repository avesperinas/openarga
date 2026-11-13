from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "apps" / "library.md"
LINK = re.compile(r"\]\(([^)#]+)(?:#[^)]*)?\)")


def test_every_relative_link_of_the_library_doc_resolves() -> None:
    targets = [one for one in LINK.findall(DOC.read_text(encoding="utf-8")) if "://" not in one]

    assert targets
    missing = [one for one in targets if not (DOC.parent / one).resolve().exists()]
    assert missing == []
