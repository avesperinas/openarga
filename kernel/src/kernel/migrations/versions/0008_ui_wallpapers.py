from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_ui_wallpapers"
down_revision: str | None = "0007_ui_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ui_wallpapers",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("variant", sa.Text, primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("content_type", sa.Text, nullable=False),
        sa.Column("bytes", sa.LargeBinary, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column(
            "measured",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("variant in ('image', 'blurred')", name="ui_wallpapers_variant"),
        schema="kernel",
    )
    op.create_index(
        "ui_wallpapers_by_subject",
        "ui_wallpapers",
        ["subject", "created_at"],
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_index("ui_wallpapers_by_subject", table_name="ui_wallpapers", schema="kernel")
    op.drop_table("ui_wallpapers", schema="kernel")
