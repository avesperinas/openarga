from collections.abc import Sequence

from alembic import op

revision: str = "0030_notification_delivery"
down_revision: str | None = "0029_wallpaper_variants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        alter table kernel.push_subscription
            add column if not exists last_error text
                check (last_error is null or length(last_error) <= 300),
            add column if not exists last_error_at timestamptz
    """)
    op.execute("""
        alter table kernel.notification
            add column if not exists attempts smallint not null default 0,
            add column if not exists send_after timestamptz
    """)


def downgrade() -> None:
    op.execute("""
        alter table kernel.notification
            drop column if exists send_after,
            drop column if exists attempts
    """)
    op.execute("""
        alter table kernel.push_subscription
            drop column if exists last_error_at,
            drop column if exists last_error
    """)
