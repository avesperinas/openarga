from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from hub import capabilities, extractors, sync
from hub.providers import imap

MAILBOX = {"host": "imap.correo.invalid", "port": "993", "username": "buzon@ejemplo.local"}
PASSWORD = "abcd efgh ijkl mnop"
SENDER = "Gestora Inventada <avisos@ejemplo.com>"

VALUE = re.compile(r"Valor de tu cartera a (\d{2}/\d{2}/\d{4}): ([\d.,]+) €")
CONTRIBUTION = re.compile(r"Aportación del (\d{2}/\d{2}/\d{4}): ([\d.,]+) €")


def day(raw: str) -> date:
    return datetime.strptime(raw, "%d/%m/%Y").date()


def parse(message: EmailMessage) -> list[extractors.Fact]:
    body = extractors.body_text(message)
    value = VALUE.search(body)
    if value is None:
        raise extractors.ExtractorError("no está el valor de la cartera")
    facts: list[extractors.Fact] = [
        extractors.Balance(
            "cartera",
            "Cartera de la gestora",
            day(value.group(1)),
            extractors.euros(value.group(2)),
        )
    ]
    facts += [
        extractors.Movement(
            "cartera",
            day(found.group(1)),
            extractors.euros(found.group(2)),
            description="Aportación",
            kind="contribution",
        )
        for found in CONTRIBUTION.finditer(body)
    ]
    return facts


GESTORA = extractors.Extractor(
    id="gestora",
    entity="Gestora Inventada",
    category="finance",
    sender=re.compile(r"@ejemplo\.com"),
    subject=re.compile(r"^(Fwd?: )?Tu cartera a"),
    parse=parse,
)


def message(sender: str, subject: str, body: str, when: datetime) -> EmailMessage:
    built = EmailMessage()
    built["From"] = sender
    built["Subject"] = subject
    built["Date"] = format_datetime(when)
    built["Message-ID"] = make_msgid()
    built.set_content(body)
    return built


STATEMENT = (
    "Hola,\n\nValor de tu cartera a 31/08/2026: 12.345,67 €\n"
    "Aportación del 05/08/2026: 150,00 €\n\nUn saludo."
)
AUGUST = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


class FakeMailbox:
    def __init__(self, messages: list[EmailMessage]) -> None:
        self.messages = messages
        self.opened: list[str] = []
        self.logins: list[tuple[str, str]] = []

    def headers(self, since: date) -> list[imap.Header]:
        return [
            imap.header_of(str(uid), found)
            for uid, found in enumerate(self.messages)
            if imap.header_of(str(uid), found).received.date() >= since
        ]

    def message(self, uid: str) -> EmailMessage:
        self.opened.append(uid)
        return self.messages[int(uid)]

    def close(self) -> None:
        return None


@pytest.fixture
def mailbox(monkeypatch) -> FakeMailbox:
    fake = FakeMailbox([])

    def opener(config, password):
        fake.logins.append((config["username"], password))
        return fake

    monkeypatch.setattr(imap, "OPENER", [opener])
    monkeypatch.setitem(extractors.EXTRACTORS, GESTORA.id, GESTORA)
    return fake


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


async def connect(api) -> str:
    response = await api.post(
        "/connections",
        json={
            "provider": "imap",
            "label": "Buzón",
            "settings": MAILBOX,
            "secrets": {"password": PASSWORD},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def read(connection: str, kernel) -> sync.Outcome:
    from hub.db import as_module

    async with as_module() as database:
        row = (
            await database.execute(
                text(
                    "select id, provider, label, config, consent_expires_at "
                    "from hub.hub_connection where id = :id"
                ),
                {"id": UUID(connection)},
            )
        ).one()
    async with httpx.AsyncClient() as source:
        return await sync.run(SimpleNamespace(**row._mapping), source=source, kernel=kernel)


async def events(schema, event_type: str) -> list:
    async with schema.connect() as connection:
        return (
            await connection.execute(
                text(
                    "select payload, dedup_hash from kernel.events "
                    "where module = 'hub' and type = :type order by dedup_hash"
                ),
                {"type": event_type},
            )
        ).all()


async def test_the_mailbox_is_connected_with_where_it_is_and_its_app_password(api) -> None:
    connection = await connect(api)
    wrong = await api.post(
        "/connections",
        json={
            "provider": "imap",
            "settings": {**MAILBOX, "host": "no es un servidor"},
            "secrets": {"password": "x"},
        },
    )

    ficha = (await api.get(f"/connections/{connection}")).json()
    assert ficha["settings"] == {
        "host": "imap.correo.invalid",
        "port": 993,
        "username": "buzon@ejemplo.local",
        "folder": "INBOX",
    }
    assert [s["key"] for s in ficha["secrets"]] == ["password"]
    assert PASSWORD not in str(ficha)
    assert wrong.status_code == 422
    assert "imap.gmail.com" in wrong.json()["detail"]


async def test_a_synthetic_statement_enters_as_a_valuation(api, kernel, schema, mailbox) -> None:
    mailbox.messages = [
        message(SENDER, "Tu cartera a 31/08/2026", STATEMENT, AUGUST),
        message("Otra <hola@example.org>", "Tu cartera a 31/08/2026", "Nada que ver", AUGUST),
    ]
    connection = await connect(api)

    outcome = await read(connection, kernel)

    assert (outcome.outcome, outcome.emitted) == ("ok", 3)
    [balance] = await events(schema, "finance.balance")
    assert balance.dedup_hash == "mail:gestora:cartera:2026-08-31"
    assert (balance.payload["amount"], balance.payload["account"]) == (
        "12345.67",
        "mail:gestora:cartera",
    )
    [movement] = await events(schema, "finance.movement")
    assert movement.payload["amount"] == "150.00"
    assert movement.dedup_hash == "mail:gestora:cartera:2026-08-05:150.00:contribution"
    [account] = await events(schema, "finance.account")
    assert account.payload["bank"] == "Gestora Inventada"
    assert mailbox.opened == ["0"]
    assert mailbox.logins == [("buzon@ejemplo.local", PASSWORD)]


async def test_forwarding_the_same_mail_twice_is_one_fact(api, kernel, schema, mailbox) -> None:
    mailbox.messages = [
        message(SENDER, "Tu cartera a 31/08/2026", STATEMENT, AUGUST),
        message(SENDER, "Fwd: Tu cartera a 31/08/2026", STATEMENT, AUGUST),
    ]
    connection = await connect(api)

    outcome = await read(connection, kernel)

    assert mailbox.messages[0]["Message-ID"] != mailbox.messages[1]["Message-ID"]
    assert (outcome.outcome, outcome.emitted, outcome.duplicated) == ("ok", 3, 3)
    assert len(await events(schema, "finance.balance")) == 1
    assert len(await events(schema, "finance.movement")) == 1


async def test_a_changed_format_fails_loudly_and_says_which_and_when(
    api, kernel, schema, mailbox
) -> None:
    changed = "Hola,\n\nEl patrimonio gestionado es de 12.345,67 €\n"
    mailbox.messages = [message(SENDER, "Tu cartera a 31/08/2026", changed, AUGUST)]
    connection = await connect(api)

    first = await read(connection, kernel)
    await read(connection, kernel)

    assert first.outcome == "error"
    assert first.detail == (
        "Gestora Inventada no entiende su correo del 01/09/2026: no está el valor de la cartera"
    )
    assert await events(schema, "finance.balance") == []
    ficha = (await api.get(f"/connections/{connection}")).json()
    assert ficha["state"] == "failing"
    assert "Gestora Inventada no entiende" in ficha["reason"]
    assert ficha["extractors"] == [{"id": "gestora", "entity": "Gestora Inventada"}]


async def test_without_extractors_the_mailbox_is_read_and_says_so(
    api, kernel, mailbox, monkeypatch
) -> None:
    monkeypatch.delitem(extractors.EXTRACTORS, GESTORA.id)
    mailbox.messages = [message(SENDER, "Tu cartera a 31/08/2026", STATEMENT, AUGUST)]
    connection = await connect(api)

    outcome = await read(connection, kernel)

    assert (outcome.outcome, outcome.emitted) == ("ok", 0)
    assert "Sin reglas" in outcome.detail
    assert mailbox.opened == []


async def test_each_entity_it_reads_is_in_its_category_by_mail(api, mailbox) -> None:
    finance = next(c for c in (await api.get("/catalogue")).json() if c["id"] == "finance")

    [gestora] = [p for p in finance["providers"] if p.get("by_mail")]
    assert (gestora["id"], gestora["name"]) == ("imap.gestora", "Gestora Inventada")


def test_an_amount_that_is_not_one_is_a_changed_format() -> None:
    assert extractors.euros("12.345,67") == Decimal("12345.67")
    with pytest.raises(extractors.ExtractorError):
        extractors.euros("doce")


VALUE_RULE = {
    "entity": "Gestora Inventada",
    "product": "Plan de pensiones",
    "sender": "avisos@ejemplo.com",
    "subject": "tu plan",
    "anchor": "Valor de tu plan:",
    "fact": "balance",
}
DEPOSIT_RULE = {
    **VALUE_RULE,
    "subject": "aportación recibida",
    "anchor": "Has aportado",
    "fact": "deposit",
}
PLAN = "mail:rules:gestora-inventada-plan-de-pensiones"


async def rules_of(api, connection: str, *rules: dict):
    return await api.put(f"/connections/{connection}/rules", json={"rules": list(rules)})


async def test_rules_are_kept_on_the_mailbox_and_checked(api, mailbox) -> None:
    connection = await connect(api)

    saved = await rules_of(api, connection, VALUE_RULE)
    missing = await rules_of(api, connection, {**VALUE_RULE, "anchor": ""})
    wrong_fact = await rules_of(api, connection, {**VALUE_RULE, "fact": "gasto"})

    assert saved.status_code == 200, saved.text
    [rule] = saved.json()["rules"]
    assert {k: rule[k] for k in VALUE_RULE} == VALUE_RULE
    assert len(rule["id"]) >= 8
    assert missing.status_code == 422
    assert "antes del importe" in missing.json()["detail"]
    assert wrong_fact.status_code == 422
    again = await rules_of(api, connection, {**rule, "anchor": "Valor:"})
    assert [(r["id"], r["anchor"]) for r in again.json()["rules"]] == [(rule["id"], "Valor:")]


async def test_rules_only_go_on_a_mailbox_of_yours(api, mailbox) -> None:
    nobody = "00000000-0000-0000-0000-000000000000"

    assert (await rules_of(api, nobody, VALUE_RULE)).status_code == 404


async def test_a_rule_turns_its_mail_into_a_value_and_a_contribution(
    api, kernel, schema, mailbox
) -> None:
    mailbox.messages = [
        message(SENDER, "Así va tu plan", "Hola.\nValor de tu plan: 8.410,25 €\nGracias.", AUGUST),
        message(
            SENDER, "Fwd: Así va tu plan", "Hola.\nValor de tu plan: 8.410,25 €\nGracias.", AUGUST
        ),
        message(SENDER, "Aportación recibida", "Has aportado 100,00 € a tu plan.", AUGUST),
        message("Otra <hola@example.org>", "Así va tu plan", "Valor de tu plan: 1 €", AUGUST),
    ]
    monkeypatch_free = extractors.EXTRACTORS.pop(GESTORA.id)
    try:
        connection = await connect(api)
        await rules_of(api, connection, VALUE_RULE, DEPOSIT_RULE)

        outcome = await read(connection, kernel)
    finally:
        extractors.EXTRACTORS[GESTORA.id] = monkeypatch_free

    assert outcome.outcome == "ok", outcome.detail
    [balance] = await events(schema, "finance.balance")
    assert (balance.payload["account"], balance.payload["amount"]) == (PLAN, "8410.25")
    assert balance.payload["on"] == "2026-09-01"
    [movement] = await events(schema, "finance.movement")
    assert (movement.payload["account"], movement.payload["amount"]) == (PLAN, "100.00")
    assert movement.payload["nature"] == "contribution"
    [account] = await events(schema, "finance.account")
    assert (account.payload["bank"], account.payload["name"]) == (
        "Gestora Inventada",
        "Plan de pensiones",
    )
    assert "3" not in mailbox.opened


async def test_a_rule_is_announced_before_its_first_mail(api, kernel, schema, mailbox) -> None:
    connection = await connect(api)
    await rules_of(api, connection, VALUE_RULE)

    outcome = await read(connection, kernel)

    assert outcome.outcome == "ok"
    [account] = await events(schema, "finance.account")
    assert account.payload["account"] == PLAN
    assert account.payload["connection"] == connection


async def test_a_rule_that_no_longer_finds_its_text_fails_loudly(
    api, kernel, schema, mailbox
) -> None:
    mailbox.messages = [message(SENDER, "Así va tu plan", "Tu saldo es 8.410,25 €", AUGUST)]
    connection = await connect(api)
    await rules_of(api, connection, VALUE_RULE)

    outcome = await read(connection, kernel)

    assert outcome.outcome == "error"
    assert "Gestora Inventada no entiende su correo del 01/09/2026" in outcome.detail
    assert "Valor de tu plan:" in outcome.detail
    assert await events(schema, "finance.balance") == []


async def test_trying_a_rule_reads_the_mail_there_is_and_publishes_nothing(
    api, kernel, schema, mailbox
) -> None:
    now = datetime.now(UTC)
    mailbox.messages = [
        message(SENDER, "Así va tu plan", "Valor de tu plan: 8.000,00 €", now.replace(day=1)),
        message(SENDER, "Así va tu plan", "Ha cambiado el formato", now),
    ]
    connection = await connect(api)

    tried = await api.post(f"/connections/{connection}/rules/try", json=VALUE_RULE)

    assert tried.status_code == 200, tried.text
    newest, older = tried.json()["results"]
    assert newest["amount"] is None and "no aparece" in newest["problem"]
    assert (older["amount"], older["problem"]) == ("8000.00", None)
    assert await events(schema, "finance.balance") == []
    assert (await api.get(f"/connections/{connection}")).json()["rules"] == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Valor: 1.234,56 €", "1234.56"),
        ("Valor: 12.345 €", "12345"),
        ("Valor: € 980,5 y más", "980.5"),
        ("Valor: 1 234,56 EUR", "1234.56"),
        ("Valor: -300,00", "-300.00"),
        ("Valor 42", "42"),
    ],
)
def test_the_amount_after_the_text_is_read_in_spanish(body: str, expected: str) -> None:
    from hub import rules

    assert rules.amount_after(body, "Valor") == Decimal(expected)


@pytest.mark.parametrize("body", ["Valor: 1,234.56 €", "Valor: 12.34", "Valor: pendiente"])
def test_what_is_not_a_spanish_amount_is_a_changed_format(body: str) -> None:
    from hub import rules

    with pytest.raises(extractors.ExtractorError):
        rules.amount_after(body, "Valor")
