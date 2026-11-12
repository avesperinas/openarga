from collections.abc import Sequence

from alembic import op

revision: str = "0033_person_preferences"
down_revision: str | None = "0032_old_desktops_gone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT = "nullif(current_setting('arga.user_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"""
        create table kernel.person_preferences (
            user_id     uuid primary key default {CURRENT}
                        references kernel.users (id) on delete cascade,
            locale      text check (locale in ('en', 'es')),
            timezone    text check (length(timezone) between 1 and 64),
            currency    text check (currency ~ '^[A-Z]{{3}}$'),
            country     text check (country ~ '^[A-Z]{{2}}$'),
            region      text check (region ~ '^[A-Z]{{2}}-[A-Z0-9]{{1,3}}$'),
            area        text check (area ~ '^[a-z0-9][a-z0-9-]{{0,63}}$'),
            updated_at  timestamptz not null default now()
        )
    """)
    op.execute("comment on table kernel.person_preferences is 'arga:person'")
    op.execute("alter table kernel.person_preferences enable row level security")
    op.execute("alter table kernel.person_preferences force row level security")
    op.execute(
        "create policy arga_owner on kernel.person_preferences "
        f"using (user_id = (select {CURRENT})) with check (user_id = (select {CURRENT}))"
    )


def downgrade() -> None:
    op.execute("drop table kernel.person_preferences")
