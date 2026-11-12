from collections.abc import Sequence

from alembic import op

revision: str = "0019_space_leave"
down_revision: str | None = "0018_ui_desktops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table kernel.space_members add column left_at timestamptz")
    op.execute(
        "alter table kernel.space_members drop constraint space_members_status_check, "
        "add constraint space_members_status_check "
        "check (status in ('pending', 'accepted', 'left'))"
    )


def downgrade() -> None:
    op.execute("delete from kernel.space_members where status = 'left'")
    op.execute(
        "alter table kernel.space_members drop constraint space_members_status_check, "
        "add constraint space_members_status_check check (status in ('pending', 'accepted'))"
    )
    op.execute("alter table kernel.space_members drop column left_at")
