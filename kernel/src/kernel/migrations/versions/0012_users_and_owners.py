from collections.abc import Sequence

from alembic import op

revision: str = "0012_users_and_owners"
down_revision: str | None = "0011_module_migrations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_USER = "nullif(current_setting('arga.user_id', true), '')::uuid"

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
SYSTEM = ("modules", "module_migrations", "users")

USERS = """
create table kernel.users (
    id           uuid primary key default gen_random_uuid(),
    subject      text not null unique,
    created_at   timestamptz not null default now(),
    last_seen_at timestamptz
)
"""

EXISTING = """
insert into kernel.users (subject)
select subject from kernel.ui_layouts where subject not like '%@%'
union
select subject from kernel.ui_preferences where subject not like '%@%'
union
select subject from kernel.ui_wallpapers where subject not like '%@%'
on conflict (subject) do nothing
"""


def upgrade() -> None:
    op.execute(USERS)
    op.execute(EXISTING)
    for table in PERSON:
        op.execute(
            f"alter table kernel.{table} add column if not exists user_id uuid "
            f"default {CURRENT_USER}"
        )
        op.execute(f"comment on table kernel.{table} is 'arga:person'")
    for table in SYSTEM:
        op.execute(f"comment on table kernel.{table} is 'arga:system'")
    op.execute("comment on table public.alembic_version is 'arga:system'")


def downgrade() -> None:
    for table in PERSON:
        op.execute(f"alter table kernel.{table} drop column if exists user_id")
    op.execute("drop table kernel.users")
