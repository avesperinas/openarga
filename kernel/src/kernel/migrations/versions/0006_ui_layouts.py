from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_ui_layouts"
down_revision: str | None = "0005_entity_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ui_layouts",
        sa.Column("subject", sa.Text, primary_key=True),
        sa.Column("breakpoint", sa.Text, primary_key=True),
        sa.Column(
            "pages",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "breakpoint in ('mobile','tablet','desktop')", name="breakpoint_is_known"
        ),
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_table("ui_layouts", schema="kernel")
