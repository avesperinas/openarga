from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_module_heartbeat"
down_revision: str | None = "0014_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "modules",
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_column("modules", "registered_at", schema="kernel")
