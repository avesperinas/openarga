from collections.abc import Sequence

from alembic import op

revision: str = "0022_ui_device_desktops"
down_revision: str | None = "0021_module_receives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT = "nullif(current_setting('arga.user_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"""
        create table kernel.ui_device_desktops (
            user_id    uuid not null default {CURRENT},
            device     text not null check (device in ('mobile', 'desktop')),
            pages      jsonb not null default '[]'::jsonb,
            placements jsonb not null default '{{}}'::jsonb,
            updated_at timestamptz not null default now(),
            primary key (user_id, device)
        )
    """)
    op.execute("comment on table kernel.ui_device_desktops is 'arga:person'")
    op.execute("alter table kernel.ui_device_desktops enable row level security")
    op.execute("alter table kernel.ui_device_desktops force row level security")
    op.execute(
        f"create policy arga_owner on kernel.ui_device_desktops "
        f"using (user_id = {CURRENT}) with check (user_id = {CURRENT})"
    )


def downgrade() -> None:
    op.execute("drop table kernel.ui_device_desktops")
