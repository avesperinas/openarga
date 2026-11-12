from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from arga_tenancy import as_user
from kernel.db import engine
from kernel.entities import find_matches, in_family, last_word, merge_entities, surviving
from kernel.identity import AUTO_MERGE_CONFIDENCE

CANDIDATES = text("""
    select cast(id as text) as id, name
    from kernel.entities
    where status = 'candidate'
    order by created_at, id
""")

OLDER_OF = text("""
    select cast(id as text) as id, name
    from kernel.entities
    where id in (cast(:left as uuid), cast(:right as uuid))
    order by created_at, id
    limit 1
""")


@dataclass(frozen=True)
class Merged:
    candidate: str
    candidate_name: str
    target: str
    target_name: str
    rule: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class Abstained:
    entity: str
    name: str
    best_name: str | None
    best_confidence: float | None
    reason: str = "por debajo del umbral"


@dataclass
class Outcome:
    examined: int = 0
    merged: list[Merged] = field(default_factory=list)
    abstained: list[Abstained] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.merged)


async def run(connection: AsyncConnection) -> Outcome:
    outcome = Outcome()
    candidates = (await connection.execute(CANDIDATES)).all()

    for candidate in candidates:
        alive = await surviving(connection, candidate.id)
        if alive != candidate.id:
            continue

        outcome.examined += 1
        matches = await find_matches(connection, candidate.id)
        best = next((item for item in matches.candidates if item.would_merge), None)

        if best is None:
            weakest = matches.candidates[0] if matches.candidates else None
            outcome.abstained.append(
                Abstained(
                    entity=candidate.id,
                    name=candidate.name,
                    best_name=weakest.name if weakest else None,
                    best_confidence=weakest.confidence if weakest else None,
                )
            )
            continue

        target = await surviving(connection, best.entity_id)
        if target is None or target == candidate.id:
            continue

        older = (await connection.execute(OLDER_OF, {"left": candidate.id, "right": target})).one()
        winner, winner_name = older.id, older.name
        loser, loser_name = (
            (target, best.name) if winner == candidate.id else (candidate.id, candidate.name)
        )

        if await in_family(connection, winner, loser):
            continue

        if await last_word(connection, loser, winner) == "rejected":
            outcome.abstained.append(
                Abstained(
                    entity=candidate.id,
                    name=candidate.name,
                    best_name=best.name,
                    best_confidence=best.confidence,
                    reason="descartado antes",
                )
            )
            continue

        await merge_entities(
            connection,
            loser,
            winner,
            method="rule",
            decided_by="resolver",
            rule=best.rule,
            confidence=best.confidence,
            evidence=best.evidence,
        )
        outcome.merged.append(
            Merged(
                candidate=loser,
                candidate_name=loser_name,
                target=winner,
                target_name=winner_name,
                rule=best.rule,
                confidence=best.confidence,
                evidence=best.evidence,
            )
        )

    return outcome


async def _run() -> Outcome:
    try:
        async with engine().connect() as connection:
            users = [
                row.id for row in await connection.execute(text("select id from kernel.users"))
            ]
        total = Outcome()
        for user in users or [None]:
            with as_user(user):
                async with engine().begin() as connection:
                    outcome = await run(connection)
            total.examined += outcome.examined
            total.merged.extend(outcome.merged)
            total.abstained.extend(outcome.abstained)
        return total
    finally:
        await engine().dispose()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        print("uso: python -m kernel.resolver", file=sys.stderr)
        return 2

    try:
        outcome = asyncio.run(_run())
    except Exception as error:  # noqa: BLE001 - se traduce a un exit code, no se traga
        print(f"pasada fallida: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    for decision in outcome.merged:
        print(
            f"fusionada  {decision.candidate_name!r} -> {decision.target_name!r}"
            f"  {decision.rule} {decision.confidence}  · {decision.evidence}"
        )
    for skipped in outcome.abstained:
        best = (
            f"lo más parecido: {skipped.best_name!r} ({skipped.best_confidence})"
            if skipped.best_name
            else "nada parecido"
        )
        print(f"se abstiene {skipped.name!r}  · {best} · {skipped.reason}")
    print(
        f"{outcome.examined} candidata(s) · {len(outcome.merged)} fusionada(s) · "
        f"{len(outcome.abstained)} sin resolver · umbral {AUTO_MERGE_CONFIDENCE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
