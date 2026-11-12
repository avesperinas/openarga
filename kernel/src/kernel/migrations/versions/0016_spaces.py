from collections.abc import Sequence

from alembic import op

revision: str = "0016_spaces"
down_revision: str | None = "0015_module_heartbeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    """
    create table kernel.spaces (
        id         uuid primary key default gen_random_uuid(),
        name       text not null check (length(name) between 1 and 80),
        created_at timestamptz not null default now()
    )
    """,
    """
    create table kernel.space_members (
        space_id   uuid not null references kernel.spaces(id) on delete cascade,
        user_id    uuid not null references kernel.users(id) on delete cascade,
        role       text not null check (role in ('owner', 'member')),
        status     text not null check (status in ('pending', 'accepted')),
        created_at timestamptz not null default now(),
        primary key (space_id, user_id)
    )
    """,
    "create index space_members_by_user on kernel.space_members (user_id)",
    """
    create table kernel.space_invites (
        code       text primary key,
        space_id   uuid not null references kernel.spaces(id) on delete cascade,
        created_by uuid not null references kernel.users(id) on delete cascade,
        expires_at timestamptz not null,
        used_at    timestamptz,
        used_by    uuid references kernel.users(id) on delete set null
    )
    """,
)


def upgrade() -> None:
    for statement in TABLES:
        op.execute(statement)
    for table in ("spaces", "space_members", "space_invites"):
        op.execute(f"comment on table kernel.{table} is 'arga:system'")


def downgrade() -> None:
    op.execute("drop table kernel.space_invites")
    op.execute("drop table kernel.space_members")
    op.execute("drop table kernel.spaces")
