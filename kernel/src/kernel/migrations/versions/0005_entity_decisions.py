from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_entity_decisions"
down_revision: str | None = "0004_entity_resolution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PAIR_KEY = "least(loser_id, winner_id)::text || ':' || greatest(loser_id, winner_id)::text"


def upgrade() -> None:
    op.create_table(
        "entity_decisions",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "loser_id",
            sa.UUID,
            sa.ForeignKey("kernel.entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "winner_id",
            sa.UUID,
            sa.ForeignKey("kernel.entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pair_key",
            sa.Text,
            sa.Computed(PAIR_KEY, persisted=True),
            nullable=False,
        ),
        sa.Column("decision", sa.Text, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("rule", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("evidence", sa.Text),
        sa.Column("decided_by", sa.Text, nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("decision in ('merged','rejected')", name="decision_is_known"),
        sa.CheckConstraint("loser_id <> winner_id", name="a_pair_needs_two"),
        schema="kernel",
    )
    op.create_index(
        "entity_decisions_pair_idx",
        "entity_decisions",
        ["pair_key", sa.text("decided_at desc")],
        schema="kernel",
    )
    op.create_index("entity_decisions_loser_idx", "entity_decisions", ["loser_id"], schema="kernel")


def downgrade() -> None:
    op.drop_table("entity_decisions", schema="kernel")
