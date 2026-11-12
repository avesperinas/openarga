from collections.abc import Sequence

from alembic import op

revision: str = "0031_notification_read"
down_revision: str | None = "0030_notification_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table kernel.notification add column if not exists read_at timestamptz")


def downgrade() -> None:
    op.execute("alter table kernel.notification drop column if exists read_at")
