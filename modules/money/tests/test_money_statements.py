from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from money_people import OTHER

from arga_tenancy import current_user
from money import book as books
from money import statements


@pytest.fixture(autouse=True)
def fresh_cache():
    books._CACHE.clear()
    yield
    books._CACHE.clear()


CSV_SEMICOLON = """Date;Description;Amount;Balance
15/03/2026;Coffee Corner;-3,40;996,60
16/03/2026;Salary March;1.250,00;2.246,60
16/03/2026;Coffee Corner;-3,40;2.243,20
16/03/2026;Coffee Corner;-3,40;2.239,80
"""

CSV_SPLIT = """booking date,details,debit,credit
2026-03-01,Rent,650.00,
2026-03-02,Refund,,12.50
"""

OFX_SGML = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<CURDEF>EUR
<BANKACCTFROM><BANKID>0000<ACCTID>ES0000000000000000009999<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260301
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260305120000
<TRNAMT>-42.10
<FITID>20260305-1
<NAME>Grocery Store
<MEMO>Card payment
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260310
<TRNAMT>1500.00
<FITID>20260310-1
<NAME>Employer
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>2457.90<DTASOF>20260311</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""

OFX_XML = """<?xml version="1.0"?>
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><DTPOSTED>20260320</DTPOSTED><TRNAMT>-9.99</TRNAMT><FITID>x1</FITID><NAME>Streaming</NAME></STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>100.00</BALAMT><DTASOF>20260321</DTASOF></LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("-3,40", "-3.40"),
        ("1.250,00", "1250.00"),
        ("1,250.00", "1250.00"),
        ("(12.50)", "-12.50"),
        ("12.5", "12.5"),
        ("1.234.567", "1234567"),
        ("€ 7,5", "7.5"),
    ],
)
def test_amounts_are_read_in_both_notations(raw: str, expected: str) -> None:
    assert statements.amount_of(raw) == Decimal(expected)


def test_a_csv_with_semicolons_and_decimal_commas() -> None:
    parsed = statements.parse(CSV_SEMICOLON)
    assert [line.amount for line in parsed.lines] == [
        Decimal("-3.40"),
        Decimal("1250.00"),
        Decimal("-3.40"),
        Decimal("-3.40"),
    ]
    assert parsed.lines[1].booked_on == date(2026, 3, 16)
    assert parsed.balance == (date(2026, 3, 16), Decimal("2239.80"))
    assert len({line.reference for line in parsed.lines}) == 4


def test_a_csv_with_debit_and_credit_columns() -> None:
    parsed = statements.parse(CSV_SPLIT)
    assert [line.amount for line in parsed.lines] == [Decimal("-650.00"), Decimal("12.50")]


def test_the_columns_can_be_named() -> None:
    parsed = statements.parse(
        "Day,Note,Sum\n2026-01-02,Gift,5.00\n",
        columns={"booked_on": "Day", "description": "Note", "amount": "Sum"},
    )
    assert parsed.lines[0].description == "Gift"


def test_a_file_that_cannot_be_read_says_where() -> None:
    with pytest.raises(statements.Unreadable, match="line 2"):
        statements.parse("date,amount\nnot a day,1\n")
    with pytest.raises(statements.Unreadable, match="no date column"):
        statements.parse("a,b\n1,2\n")


def test_an_ofx_in_sgml_and_one_in_xml() -> None:
    sgml = statements.parse(OFX_SGML)
    assert [(x.reference, x.amount, x.description) for x in sgml.lines] == [
        ("20260305-1", Decimal("-42.10"), "Grocery Store Card payment"),
        ("20260310-1", Decimal("1500.00"), "Employer"),
    ]
    assert sgml.lines[0].booked_on == date(2026, 3, 5)
    assert sgml.balance == (date(2026, 3, 11), Decimal("2457.90"))
    xml = statements.parse(OFX_XML)
    assert xml.lines[0].amount == Decimal("-9.99") and xml.balance[1] == Decimal("100.00")


async def test_a_csv_and_an_ofx_land_in_the_account_and_twice_changes_nothing(api) -> None:
    created = await api.post(
        "/accounts", json={"name": "Everyday", "type": "current", "institution": "Test Bank"}
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]

    first = await api.post(f"/accounts/{key}/statement", json={"content": CSV_SEMICOLON})
    assert first.status_code == 200, first.text
    assert first.json() == {"lines": 4, "new": 4, "balance": True}
    again = await api.post(f"/accounts/{key}/statement", json={"content": CSV_SEMICOLON})
    assert again.json()["new"] == 0
    ofx = await api.post(f"/accounts/{key}/statement", json={"content": OFX_SGML})
    assert ofx.json() == {"lines": 2, "new": 2, "balance": True}

    march = await api.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})
    rows = march.json()["movements"]
    assert len(rows) == 6
    assert {r["amount"] for r in rows} >= {-42.1, 1500.0, 1250.0}
    assert all(r["account"] == key for r in rows)


async def test_a_statement_needs_an_account_and_a_readable_file(api) -> None:
    missing = await api.post("/accounts/nope/statement", json={"content": CSV_SPLIT})
    assert missing.status_code == 404
    unreadable = await api.post("/accounts/nope/statement", json={"content": "a,b\n1,2\n"})
    assert unreadable.status_code == 422


async def test_what_is_imported_is_only_the_persons(api) -> None:
    created = await api.post(
        "/accounts", json={"name": "Everyday", "type": "current", "institution": "Test Bank"}
    )
    key = created.json()["key"]
    await api.post(f"/accounts/{key}/statement", json={"content": CSV_SPLIT})
    mine = await api.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})
    assert len(mine.json()["movements"]) == 2

    token = current_user.set(OTHER)
    try:
        theirs = await api.get("/movements", params={"from": "2026-03-01", "to": "2026-03-31"})
        assert theirs.json()["movements"] == []
        refused = await api.post(f"/accounts/{key}/statement", json={"content": CSV_SPLIT})
        assert refused.status_code == 404
    finally:
        current_user.reset(token)
