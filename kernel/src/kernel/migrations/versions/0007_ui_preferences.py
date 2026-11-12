from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_ui_preferences"
down_revision: str | None = "0006_ui_layouts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ui_preferences",
        sa.Column("subject", sa.Text, primary_key=True),
        sa.Column(
            "prefs",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_table("ui_preferences", schema="kernel")
