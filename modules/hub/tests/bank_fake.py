from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

BANK = "Banco Inventado"
APP_ID = "0f0e0d0c-aaaa-4bbb-8ccc-000000000001"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
SESSION = "5e55a000-0000-4000-8000-000000000001"
ACCOUNT = "hash-estable"
IBAN = "ES0000000000000000001234"
OTHER_IBAN = "ES0000000000000000005678"


def unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class FakeEnableBanking:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.states: list[str] = []
        self.failure: tuple[int, str] | None = None
        self.refusal: tuple[int, str] | None = None
        self.no_accounts = False
        self.valid_until = (datetime.now(UTC) + timedelta(days=180)).replace(microsecond=0)
        self.since: list[str] = []

    def check_token(self, request: httpx.Request) -> None:
        header, claims, signature = (
            request.headers["authorization"].removeprefix("Bearer ").split(".")
        )
        KEY.public_key().verify(
            unb64(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        assert json.loads(unb64(header))["kid"] == APP_ID

    @property
    def account_calls(self) -> int:
        return sum(call.endswith("/balances") for call in self.calls)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.check_token(request)
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if self.failure and path.startswith("/accounts"):
            status, code = self.failure
            return httpx.Response(status, json={"error": code, "message": "sintético"})
        if path == "/aspsps":
            return httpx.Response(
                200,
                json={
                    "aspsps": [
                        {"name": BANK, "country": "ES", "maximum_consent_validity": 15552000}
                    ]
                },
            )
        if path == "/auth":
            body = json.loads(request.content)
            if self.refusal:
                status, code = self.refusal
                return httpx.Response(status, json={"error": code, "message": "sintético"})
            self.states.append(body["state"])
            assert body["redirect_url"].endswith("/hub/callback")
            return httpx.Response(200, json={"url": f"https://banco.invalid/sca?s={body['state']}"})
        if path == "/sessions":
            return httpx.Response(200, json=self.session())
        if path.endswith("/balances"):
            return httpx.Response(
                200,
                json={
                    "balances": [
                        {
                            "balance_type": "CLBD",
                            "balance_amount": {"amount": "1830.45", "currency": "EUR"},
                            "reference_date": "2026-09-20",
                        }
                    ]
                },
            )
        if path.endswith("/details"):
            return httpx.Response(
                200, json={"account_id": {"iban": "ES00 0000 0000 0000 0000 1234"}}
            )
        if path.endswith("/transactions"):
            assert request.url.params["transaction_status"] == "BOOK"
            self.since.append(request.url.params["date_from"])
            return httpx.Response(200, json={"transactions": self.transactions()})
        return httpx.Response(404, json={"error": "NOT_FOUND", "message": path})

    def session(self) -> dict[str, Any]:
        return {
            "session_id": SESSION,
            "accounts": []
            if self.no_accounts
            else [
                {
                    "uid": "uid-de-esta-sesion",
                    "identification_hash": ACCOUNT,
                    "name": "Cuenta nómina",
                    "currency": "EUR",
                    "cash_account_type": "CACC",
                    "account_id": {"iban": "ES00 0000 0000 0000 0000 1234"},
                }
            ],
            "access": {"valid_until": self.valid_until.isoformat()},
        }

    def transactions(self) -> list[dict[str, Any]]:
        return [
            {
                "entry_reference": "REF-001",
                "transaction_amount": {"amount": "42.10", "currency": "EUR"},
                "credit_debit_indicator": "DBIT",
                "booking_date": "2026-09-18",
                "value_date": "2026-09-18",
                "creditor": {"name": "SUPERM. INVENTADO 0221"},
                "creditor_account": {"iban": "ES00 0000 0000 0000 0000 5678"},
                "bank_transaction_code": {"code": "ICDT", "sub_code": "ESCT", "description": None},
                "remittance_information": ["COMPRA TARJ. 1234"],
            },
            {
                "transaction_amount": {"amount": "5.00", "currency": "EUR"},
                "credit_debit_indicator": "DBIT",
                "booking_date": "2026-09-18",
            },
            {
                "transaction_id": "TX-777",
                "transaction_amount": {"amount": "1500.00", "currency": "EUR"},
                "credit_debit_indicator": "CRDT",
                "booking_date": "2026-09-01",
                "debtor": {"name": "EMPRESA SINTETICA SL"},
                "remittance_information": ["NOMINA"],
            },
        ]
