from collections.abc import Sequence

from alembic import op

revision: str = "0018_ui_desktops"
down_revision: str | None = "0017_module_consumes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT = "nullif(current_setting('arga.user_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"""
        create table kernel.ui_desktops (
            user_id    uuid primary key default {CURRENT},
            pages      jsonb not null default '[]'::jsonb,
            placements jsonb not null default '{{}}'::jsonb,
            updated_at timestamptz not null default now()
        )
    """)
    op.execute("comment on table kernel.ui_desktops is 'arga:person'")
    op.execute("alter table kernel.ui_desktops enable row level security")
    op.execute("alter table kernel.ui_desktops force row level security")
    op.execute(
        f"create policy arga_owner on kernel.ui_desktops "
        f"using (user_id = {CURRENT}) with check (user_id = {CURRENT})"
    )


def downgrade() -> None:
    op.execute("drop table kernel.ui_desktops")
