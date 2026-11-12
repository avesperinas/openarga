from collections.abc import Sequence

from alembic import op

revision: str = "0023_notifications"
down_revision: str | None = "0022_ui_device_desktops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT = "nullif(current_setting('arga.user_id', true), '')::uuid"
TABLES = ("push_subscription", "notification", "notification_pref")


def upgrade() -> None:
    op.execute(f"""
        create table kernel.push_subscription (
            id          uuid primary key default gen_random_uuid(),
            user_id     uuid not null default {CURRENT},
            endpoint    text not null
                        check (endpoint like 'https://%' and length(endpoint) <= 2000),
            p256dh      text not null check (length(p256dh) between 1 and 200),
            auth        text not null check (length(auth) between 1 and 100),
            name        text not null check (length(btrim(name)) between 1 and 60),
            created_at  timestamptz not null default now(),
            last_sent   timestamptz,
            unique (user_id, endpoint)
        )
    """)
    op.execute(f"""
        create table kernel.notification (
            id          uuid primary key default gen_random_uuid(),
            user_id     uuid not null default {CURRENT},
            app         text not null check (app ~ '^[a-z][a-z0-9_]{{1,30}}$'),
            kind        text not null check (kind ~ '^[a-z][a-z0-9_]{{0,40}}$'),
            key         text not null check (length(key) between 1 and 200),
            title       text not null check (length(btrim(title)) between 1 and 120),
            body        text check (body is null or length(body) <= 400),
            href        text not null check (href like '/%' and length(href) <= 300),
            due_at      timestamptz not null,
            sent_at     timestamptz,
            outcome     text check (outcome is null or length(outcome) <= 300),
            created_at  timestamptz not null default now(),
            unique (user_id, app, key)
        )
    """)
    op.execute(
        "create index notification_due on kernel.notification (due_at) where sent_at is null"
    )
    op.execute(f"""
        create table kernel.notification_pref (
            user_id     uuid not null default {CURRENT},
            app         text not null default '',
            kind        text not null default '',
            enabled     boolean,
            quiet_from  time,
            quiet_to    time,
            updated_at  timestamptz not null default now(),
            primary key (user_id, app, kind)
        )
    """)
    for table in TABLES:
        op.execute(f"comment on table kernel.{table} is 'arga:person'")
        op.execute(f"alter table kernel.{table} enable row level security")
        op.execute(f"alter table kernel.{table} force row level security")
        op.execute(
            f"create policy arga_owner on kernel.{table} "
            f"using (user_id = {CURRENT}) with check (user_id = {CURRENT})"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"drop table kernel.{table}")
