from collections.abc import Sequence

from alembic import op

revision: str = "0020_space_member_name"
down_revision: str | None = "0019_space_leave"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "alter table kernel.space_members add column display_name text "
        "constraint space_members_display_name_check "
        "check (char_length(display_name) between 1 and 40)"
    )


def downgrade() -> None:
    op.execute("alter table kernel.space_members drop column display_name")
