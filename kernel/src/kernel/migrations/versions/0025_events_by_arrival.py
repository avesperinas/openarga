from collections.abc import Sequence

from alembic import op

revision: str = "0025_events_by_arrival"
down_revision: str | None = "0024_events_type_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "events_user_type_arrival_idx",
        "events",
        ["user_id", "type", "ingested_at"],
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_index("events_user_type_arrival_idx", table_name="events", schema="kernel")
