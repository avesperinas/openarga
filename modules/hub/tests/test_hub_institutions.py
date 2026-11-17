from __future__ import annotations

import re

from hub import finance

KEYS = {"aliases", "internal", "bank_category", "merchant"}


def test_every_institution_uses_only_known_keys_and_patterns_that_compile() -> None:
    for name, data in finance.institutions().items():
        assert set(data) <= KEYS, name
        assert all(isinstance(alias, str) and alias for alias in data.get("aliases", ())), name
        if "internal" in data:
            re.compile(data["internal"])
        for pattern in [data.get("bank_category"), *data.get("merchant", ())]:
            if pattern is not None:
                assert re.compile(pattern).groups >= 1, (name, pattern)


def test_a_movement_is_read_with_the_patterns_of_its_bank() -> None:
    known = finance.institution("Revolut")

    assert finance.read(known, "Refund from Example Shop") == {"merchant": "Example Shop"}
    assert finance.institution("revolut") == known
    assert finance.institution("A bank nobody knows") == {}
