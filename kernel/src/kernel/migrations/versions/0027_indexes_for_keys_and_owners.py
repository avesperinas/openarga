from collections.abc import Sequence

from alembic import op

revision: str = "0027_indexes_for_keys_and_owners"
down_revision: str | None = "0026_policies_once_per_query"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = [
    ("entities_user_id_idx", "entities", "user_id"),
    ("entity_decisions_user_id_idx", "entity_decisions", "user_id"),
    ("entity_decisions_winner_id_idx", "entity_decisions", "winner_id"),
    ("resolution_queue_event_id_idx", "resolution_queue", "event_id"),
    ("resolution_queue_user_id_idx", "resolution_queue", "user_id"),
    ("space_invites_created_by_idx", "space_invites", "created_by"),
    ("space_invites_space_id_idx", "space_invites", "space_id"),
    ("space_invites_used_by_idx", "space_invites", "used_by"),
    ("ui_layouts_user_id_idx", "ui_layouts", "user_id"),
    ("ui_preferences_user_id_idx", "ui_preferences", "user_id"),
    ("ui_wallpapers_user_id_idx", "ui_wallpapers", "user_id"),
]


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.execute(f"create index if not exists {name} on kernel.{table} ({column})")


def downgrade() -> None:
    for name, _table, _column in INDEXES:
        op.execute(f"drop index if exists kernel.{name}")
