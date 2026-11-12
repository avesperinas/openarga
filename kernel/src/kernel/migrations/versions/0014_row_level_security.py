from collections.abc import Sequence

from alembic import op

revision: str = "0014_row_level_security"
down_revision: str | None = "0013_owner_required"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT = "nullif(current_setting('arga.user_id', true), '')::uuid"

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

KEYS = (
    "alter table kernel.events drop constraint if exists events_dedup_hash_key",
    "alter table kernel.entity_aliases drop constraint if exists entity_aliases_pkey",
    "alter table kernel.entity_aliases add constraint entity_aliases_per_person "
    "primary key using index entity_aliases_per_person",
    "alter table kernel.sync_state drop constraint if exists sync_state_pkey",
    "alter table kernel.sync_state add constraint sync_state_per_person "
    "primary key using index sync_state_per_person",
)


def upgrade() -> None:
    for statement in KEYS:
        op.execute(statement)
    for table in PERSON:
        op.execute(f"alter table kernel.{table} enable row level security")
        op.execute(f"alter table kernel.{table} force row level security")
        op.execute(
            f"create policy arga_owner on kernel.{table} "
            f"using (user_id = {CURRENT}) with check (user_id = {CURRENT})"
        )


def downgrade() -> None:
    for table in PERSON:
        op.execute(f"drop policy if exists arga_owner on kernel.{table}")
        op.execute(f"alter table kernel.{table} no force row level security")
        op.execute(f"alter table kernel.{table} disable row level security")
