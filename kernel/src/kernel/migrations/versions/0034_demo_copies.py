from collections.abc import Sequence

from alembic import op

revision: str = "0034_demo_copies"
down_revision: str | None = "0033_person_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        create table kernel.demo_copies (
            tag         text primary key check (tag ~ '^[a-z0-9]{6,16}$'),
            locale      text not null check (locale in ('en', 'es')),
            status      text not null default 'ready' check (status in ('ready', 'claimed')),
            created_at  timestamptz not null default now(),
            claimed_at  timestamptz
        )
    """)
    op.execute(
        "create index demo_copies_ready on kernel.demo_copies (locale, created_at) "
        "where status = 'ready'"
    )
    op.execute("comment on table kernel.demo_copies is 'arga:system'")


def downgrade() -> None:
    op.execute("drop table kernel.demo_copies")
