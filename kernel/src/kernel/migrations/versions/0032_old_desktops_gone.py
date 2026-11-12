from collections.abc import Sequence

from alembic import op

revision: str = "0032_old_desktops_gone"
down_revision: str | None = "0031_notification_read"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("ui_layouts", "ui_desktops", "sync_state"):
        op.execute(f"drop table if exists kernel.{table}")


def downgrade() -> None:
    pass
