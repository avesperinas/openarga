from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_entity_resolution"
down_revision: str | None = "0003_events_listing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SURVIVING_ENTITY = """
create or replace function kernel.surviving_entity(entity_id uuid)
returns uuid
language sql
stable
set search_path = pg_catalog, kernel
as $surviving$
    with recursive chain as (
        select id, merged_into from kernel.entities where id = entity_id
        union all
        select e.id, e.merged_into
        from kernel.entities e
        join chain c on e.id = c.merged_into
    )
    select id from chain where merged_into is null
$surviving$
"""

ENTITY_FAMILY = """
create or replace function kernel.entity_family(entity_id uuid)
returns setof uuid
language sql
stable
set search_path = pg_catalog, kernel
as $family$
    with recursive family as (
        select id from kernel.entities where id = entity_id
        union
        select e.id
        from kernel.entities e
        join family f on e.merged_into = f.id
    )
    select id from family
$family$
"""


def upgrade() -> None:
    op.execute("create extension if not exists pg_trgm")
    op.execute(SURVIVING_ENTITY)
    op.execute(ENTITY_FAMILY)

    op.execute(
        "create index entities_name_trgm_idx on kernel.entities using gin (name gin_trgm_ops)"
    )
    op.create_index(
        "entities_merged_into_idx",
        "entities",
        ["merged_into"],
        schema="kernel",
        postgresql_where=sa.text("merged_into is not null"),
    )


def downgrade() -> None:
    op.drop_index("entities_merged_into_idx", table_name="entities", schema="kernel")
    op.execute("drop index if exists kernel.entities_name_trgm_idx")
    op.execute("drop function if exists kernel.entity_family(uuid)")
    op.execute("drop function if exists kernel.surviving_entity(uuid)")
