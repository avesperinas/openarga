from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create schema if not exists kernel")
    op.execute("create extension if not exists pgcrypto")

    op.create_table(
        "entities",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("module", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "attrs",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB, "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="confirmed"),
        sa.Column("merged_into", sa.UUID, sa.ForeignKey("kernel.entities.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status in ('confirmed','candidate','merged')", name="entities_status_valid"
        ),
        schema="kernel",
    )
    op.create_index("entities_module_kind_idx", "entities", ["module", "kind"], schema="kernel")

    op.create_table(
        "entity_aliases",
        sa.Column(
            "entity_id",
            sa.UUID,
            sa.ForeignKey("kernel.entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.Text, primary_key=True),
        sa.Column("source", sa.Text, primary_key=True),
        sa.Column("confidence", sa.REAL, nullable=False, server_default="1.0"),
        schema="kernel",
    )
    op.create_index("entity_aliases_entity_idx", "entity_aliases", ["entity_id"], schema="kernel")

    op.create_table(
        "events",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("module", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("entity_id", sa.UUID, sa.ForeignKey("kernel.entities.id")),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("dedup_hash", sa.Text, nullable=False, unique=True),
        schema="kernel",
    )
    op.create_index(
        "events_module_ts_idx", "events", ["module", sa.text("ts desc")], schema="kernel"
    )
    op.create_index(
        "events_entity_ts_idx", "events", ["entity_id", sa.text("ts desc")], schema="kernel"
    )
    op.execute(
        "create index events_payload_idx on kernel.events using gin (payload jsonb_path_ops)"
    )

    op.create_table(
        "sync_state",
        sa.Column("connector", sa.Text, primary_key=True),
        sa.Column("cursor", sa.Text),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        schema="kernel",
    )

    op.create_table(
        "resolution_queue",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "event_id",
            sa.UUID,
            sa.ForeignKey("kernel.events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_alias", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column(
            "suggestions",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        schema="kernel",
    )
    op.execute(
        "create index resolution_pending_idx on kernel.resolution_queue (created_at) "
        "where resolved_at is null"
    )

    op.create_table(
        "modules",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("manifest", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="kernel",
    )


def downgrade() -> None:
    op.drop_table("modules", schema="kernel")
    op.drop_table("resolution_queue", schema="kernel")
    op.drop_table("sync_state", schema="kernel")
    op.drop_table("events", schema="kernel")
    op.drop_table("entity_aliases", schema="kernel")
    op.drop_table("entities", schema="kernel")
    op.execute("drop schema if exists kernel cascade")
