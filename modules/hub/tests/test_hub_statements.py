from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import capabilities, statements

TODAY = date(2026, 9, 25)
IBAN = "ES00 0000 0000 0000 0000 1234"


R = statements.RENAULT_PAGE
F = statements.FINIZENS_PAGE


def p(*texts: str) -> str:
    return "".join(f"<p>{one}</p>" for one in texts)


def renault_page(rows: list[tuple[str, str, str, str, str]]) -> str:
    body = "".join(
        f'<div class="table__body__section">{p(on)}<div class="table__body__row">'
        f"{p(on, '', kind, f'{amount}&nbsp;€', f'{after}&nbsp;€')}"
        f"<div hidden>{p(R['value_date'], on, R['concept'], concept)}</div></div></div>"
        for on, kind, amount, after, concept in rows
    )
    return (
        "<html><head><title>Renault Bank - Private Area</title>"
        "<script>var noise = '1,00 €';</script></head><body>"
        f"{p('Movement search', R['product'], IBAN, '100,00 €')}"
        f"{p('Date', 'Description', 'Amount', R['balance'])}{body}</body></html>"
    )


RENAULT_ROWS = [
    ("21/09/2026", "Transferencia", "20,00", "100,00", "TRF. PERSONA INVENTADA"),
    ("16/09/2026", "Otras operaciones", "0,50", "120,00", "LIQ.CTA.VISTA 0000"),
    ("16/09/2026", "Transferencia", "50,00", "119,50", "TRF. PERSONA INVENTADA"),
    ("01/09/2026", "Transferencia", "69,50", "69,50", "TRF. PERSONA INVENTADA"),
]


def finizens_position(plans: list[tuple[str, str, str, str]]) -> str:
    blocks = "".join(
        p(profile, "Global", name, f"{value} €", F["contributed"], "Paid in", f"{given} €")
        + p("Return", "+1,00 €", F["see_plan"])
        for profile, name, value, given in plans
    )
    return (
        "<html><head><title>Finizens</title></head><body>"
        f"{p('Consent', 'My products', F['overview'], '4 active plans')}"
        f"{p(F['plans'])}{blocks}{p(F['new_product'])}</body></html>"
    )


def finizens_movements(name: str, profile: str, entries: list[tuple[str, ...]]) -> str:
    listed = "".join(p(*entry) for entry in entries)
    return (
        "<html><head><title>Finizens</title></head><body>"
        f"{p(F['selected'], name, profile, 'Query')}"
        f"{p(F['latest'])}{listed}{p(F['own_portfolio'], 'Products')}</body></html>"
    )


def test_renault_takes_the_sign_from_the_balance() -> None:
    found = statements.read(renault_page(RENAULT_ROWS), TODAY)

    [account] = found.accounts
    assert (account.entity, account.kind, account.iban) == (
        "Renault Bank",
        "savings",
        "ES0000000000000000001234",
    )
    assert [(m.booked_on.day, m.amount) for m in found.movements] == [
        (21, Decimal("-20.00")),
        (16, Decimal("0.50")),
        (16, Decimal("50.00")),
    ]
    assert [(b.on.day, b.amount) for b in found.balances] == [
        (1, Decimal("69.50")),
        (16, Decimal("120.00")),
        (21, Decimal("100.00")),
    ]
    assert found.skipped == [
        "the oldest entry (01/09/2026, 69.50 €) does not say whether it is in or out"
    ]


def test_renault_stops_if_a_movement_is_missing() -> None:
    rows = [RENAULT_ROWS[0], RENAULT_ROWS[2], RENAULT_ROWS[3]]

    with pytest.raises(statements.StatementError, match="an entry is missing"):
        statements.read(renault_page(rows), TODAY)


def test_finizens_keeps_each_product_by_its_name() -> None:
    page = finizens_position(
        [
            ("6 - Agresivo", "Plan de Inversion - 6", "1.500,00", "1.000,00"),
            ("6 - Agresivo", "Plan de Pensiones", "520,00", "500,00"),
            ("5 - Atrevido", "Plan de Pensiones", "0,00", "-100,00"),
        ]
    )

    found = statements.read(page, TODAY)

    values = {b.account: (b.amount, b.contributed, b.on) for b in found.balances}
    assert values == {
        "statement:finizens:plan-de-inversion-6": (
            Decimal("1500.00"),
            Decimal("1000.00"),
            TODAY,
        ),
        "statement:finizens:plan-de-pensiones": (Decimal("520.00"), Decimal("400.00"), TODAY),
    }
    kinds = {a.name: a.kind for a in found.accounts}
    assert kinds == {"Plan de Inversion - 6": "roboadvisor", "Plan de Pensiones": "pension"}


def test_finizens_movements_are_capital_and_the_fees_stay_in_the_value() -> None:
    old = finizens_movements(
        "Plan de Pensiones",
        "5 - Atrevido",
        [
            ("Traspaso de Plan de Pensiones", "-400,00 €", "15/09/2026", "Se ha realizado"),
            (F["capital"][1], "+100,00 €", "09/09/2026", "Received"),
            (F["capital"][1], "+100,00 €", "09/09/2026", "Received"),
            (F["without_amount"][0], "Done", "08/09/2026", "Done"),
            (F["in_value"][0], "-0,71 €", "08/07/2026", "Charged"),
        ],
    )
    new = finizens_movements(
        "Plan de Pensiones",
        "6 - Agresivo",
        [("Traspaso de Plan de Pensiones", "+400,00 €", "16/09/2026", "Se ha recibido")],
    )

    moved = [*statements.read(old, TODAY).movements, *statements.read(new, TODAY).movements]
    fees = statements.read(old, TODAY).skipped

    assert {m.account for m in moved} == {"statement:finizens:plan-de-pensiones"}
    assert {m.nature for m in moved} == {"contribution"}
    assert sum(m.amount for m in moved) == Decimal("200.00")
    assert len({m.reference for m in moved}) == 4
    assert fees == [f"{F['in_value'][0]} of 08/07/2026: already in the plan's value"]


def test_a_page_nobody_reads_says_so() -> None:
    with pytest.raises(statements.StatementError, match="Renault Bank or Finizens"):
        statements.read("<html><title>Otra entidad</title></html>", TODAY)


@pytest.fixture
def migrated(database_url: str) -> None:
    from kernel import db as kernel_db
    from kernel import migrate

    kernel_db.engine.cache_clear()
    migrate.upgrade()


@pytest.fixture
async def kernel(migrated, schema, monkeypatch):
    from kernel import db as kernel_db
    from kernel.main import app as kernel_app

    monkeypatch.setattr(capabilities, "kernel_transport", lambda: ASGITransport(app=kernel_app))
    clean = text("delete from kernel.events where module = 'hub'")
    async with kernel_db.engine().begin() as connection:
        await connection.execute(clean)
    async with AsyncClient(transport=ASGITransport(app=kernel_app), base_url="http://kernel") as c:
        yield c
    async with kernel_db.engine().begin() as connection:
        await connection.execute(clean)
    await kernel_db.engine().dispose()


async def events(schema) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select type, source, payload from kernel.events "
                    "where module = 'hub' order by type, dedup_hash"
                )
            )
        ).all()


async def test_uploading_publishes_once_and_says_what_it_read(api, kernel, schema) -> None:
    files = {
        "files": [
            {"name": "renault.html", "content": renault_page(RENAULT_ROWS)},
            {"name": "otra.html", "content": "<html><title>Otra</title></html>"},
        ]
    }

    first = await api.post("/statements", json=files)
    again = await api.post("/statements", json=files)

    assert first.status_code == 200, first.text
    renault, other = first.json()["files"]
    assert (renault["entity"], renault["movements"], renault["balances"]) == ("Renault Bank", 3, 3)
    assert renault["new"] == 7 and renault["repeated"] == 0
    assert "Renault Bank or Finizens" in other["problem"]
    assert again.json()["files"][0]["new"] == 0
    assert again.json()["files"][0]["repeated"] == 7
    published = await events(schema)
    assert len(published) == 7
    assert {row.source for row in published} == {"statement"}
    assert sorted(row.payload["amount"] for row in published if row.type == "finance.movement") == [
        "-20.00",
        "0.50",
        "50.00",
    ]
