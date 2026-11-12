from collections.abc import Sequence

from alembic import op

revision: str = "0024_events_type_index"
down_revision: str | None = "0023_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("events_type_idx", "events", ["type"], schema="kernel")


def downgrade() -> None:
    op.drop_index("events_type_idx", table_name="events", schema="kernel")
