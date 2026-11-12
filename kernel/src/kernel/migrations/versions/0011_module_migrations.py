from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_module_migrations"
down_revision: str | None = "0010_module_reader_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "module_migrations",
        sa.Column("module", sa.Text, primary_key=True),
        sa.Column("filename", sa.Text, primary_key=True),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_table("module_migrations", schema="kernel")
