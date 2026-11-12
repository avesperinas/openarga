from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

KEY = "agenda"

Status = Literal["tentative", "confirmed", "cancelled"]

_UID = re.compile(r"^([a-z][a-z0-9_]*):([a-z][a-z0-9_]*):([A-Za-z0-9._-]+)$")
_HREF = re.compile(r"^/[a-z][a-z0-9_]*(/[A-Za-z0-9._~%-]+)*/?(\?[^\s#]*)?(#[^\s]*)?$")


class BadDated(ValueError):
    pass


def uid(module: str, kind: str, id: object) -> str:
    value = f"{module}:{kind}:{id}"
    if not _UID.match(value):
        raise BadDated(f"uid inválido: {value!r} (se espera <módulo>:<clase>:<id>)")
    return value


def _parse(value: Any, all_day: bool) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return date.fromisoformat(value) if all_day else datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{value!r} no es {'una fecha' if all_day else 'una hora'}") from error


class Dated(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: str
    title: str = Field(min_length=1, max_length=200)
    start: datetime | date
    end: datetime | date
    all_day: bool = False
    tz: str
    location: str | None = Field(default=None, max_length=300)
    status: Status = "confirmed"
    href: str

    @model_validator(mode="before")
    @classmethod
    def _dates_follow_all_day(cls, data: Any) -> Any:
        if isinstance(data, dict):
            all_day = bool(data.get("all_day", False))
            data = {
                **data,
                **{k: _parse(data[k], all_day) for k in ("start", "end") if k in data},
            }
        return data

    @field_validator("uid")
    @classmethod
    def _uid(cls, value: str) -> str:
        if not _UID.match(value):
            raise ValueError("se espera <módulo>:<clase>:<id>, como study:session:42")
        return value

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("el título no puede ir vacío")
        return value

    @field_validator("tz")
    @classmethod
    def _tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"{value!r} no es una zona IANA, como Europe/Madrid") from error
        return value

    @model_validator(mode="after")
    def _coherent(self) -> Dated:
        if self.all_day:
            for name in ("start", "end"):
                if type(getattr(self, name)) is not date:
                    raise ValueError(f"todo el día: {name} es una fecha, sin hora")
            if self.end <= self.start:
                raise ValueError("todo el día: el fin es exclusivo, un día acaba al siguiente")
        else:
            for name in ("start", "end"):
                value = getattr(self, name)
                if not isinstance(value, datetime):
                    raise ValueError(f"con hora: {name} lleva hora")
                if value.utcoffset() is None:
                    raise ValueError(f"con hora: {name} lleva zona (+02:00), no una hora suelta")
            if self.end < self.start:
                raise ValueError("el fin no puede ir antes del inicio")

        module = self.uid.split(":", 1)[0]
        if not _HREF.match(self.href) or not (
            self.href == f"/{module}"
            or self.href.startswith((f"/{module}/", f"/{module}?", f"/{module}#"))
        ):
            raise ValueError(f"href es una ruta de la app de {module}, como /{module}/…")
        return self


def _explain(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        where = ".".join(str(p) for p in item["loc"]) or "objeto"
        parts.append(f"{where}: {item['msg']}")
    return "; ".join(parts)


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return Dated.model_validate(payload).model_dump(mode="json")
    except ValidationError as error:
        raise BadDated(f"no casa con la forma común: {_explain(error)}") from None


def dated(**fields: Any) -> dict[str, Any]:
    return validate(fields)


def check_event(payload: dict[str, Any]) -> dict[str, Any]:
    if KEY not in payload:
        raise BadDated(f"el payload no lleva la clave {KEY!r}")
    return validate(payload[KEY])


__all__ = ["KEY", "BadDated", "Dated", "Status", "check_event", "dated", "uid", "validate"]
