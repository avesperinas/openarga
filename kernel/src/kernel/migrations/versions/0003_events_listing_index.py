from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_events_listing"
down_revision: str | None = "0002_module_isolation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "events_ts_id_idx",
        "events",
        [sa.text("ts desc"), sa.text("id desc")],
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_index("events_ts_id_idx", table_name="events", schema="kernel")
