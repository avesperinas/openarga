from collections.abc import Sequence

from alembic import op

revision: str = "0013_owner_required"
down_revision: str | None = "0012_users_and_owners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERSON = (
    "events",
    "entities",
    "entity_aliases",
    "resolution_queue",
    "entity_decisions",
    "sync_state",
    "ui_layouts",
    "ui_preferences",
    "ui_wallpapers",
)

PER_PERSON = (
    "create unique index if not exists events_dedup_per_person "
    "on kernel.events (user_id, dedup_hash)",
    "create unique index if not exists entity_aliases_per_person "
    "on kernel.entity_aliases (user_id, alias, source)",
    "create unique index if not exists sync_state_per_person "
    "on kernel.sync_state (user_id, connector)",
)


def backfill_sql() -> str:
    updates = "\n".join(
        f"        update kernel.{table} set user_id = owner where user_id is null;"
        for table in PERSON
    )
    checks = " or ".join(
        f"exists (select 1 from kernel.{table} where user_id is null)" for table in PERSON
    )
    return f"""
do $$
declare
    people integer;
    owner uuid;
begin
    select count(*) into people from kernel.users;
    if people = 1 then
        select id into owner from kernel.users;
{updates}
    elsif {checks} then
        raise exception 'hay filas del kernel sin dueño y % persona(s): no se puede saber de quién '
                        'son (ADR-0028). Hay que dárselas a mano antes de migrar.', people;
    end if;
end $$
"""


def upgrade() -> None:
    op.execute(backfill_sql())
    for table in PERSON:
        op.execute(f"alter table kernel.{table} alter column user_id set not null")
    for statement in PER_PERSON:
        op.execute(statement)


def downgrade() -> None:
    for name in ("events_dedup_per_person", "entity_aliases_per_person", "sync_state_per_person"):
        op.execute(f"drop index if exists kernel.{name}")
    for table in PERSON:
        op.execute(f"alter table kernel.{table} alter column user_id drop not null")
