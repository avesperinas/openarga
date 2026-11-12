from collections.abc import Sequence

from alembic import op

revision: str = "0026_policies_once_per_query"
down_revision: str | None = "0025_events_by_arrival"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT = "nullif(current_setting('arga.user_id', true), '')::uuid"


def _rewrite(rule: str) -> None:
    op.execute(
        f"""
        do $$
        declare one record;
        begin
          for one in
            select tablename from pg_policies
            where schemaname = 'kernel' and policyname = 'arga_owner'
          loop
            execute format(
              'alter policy arga_owner on kernel.%I using (%s) with check (%s)',
              one.tablename, $rule${rule}$rule$, $rule${rule}$rule$
            );
          end loop;
        end $$
        """
    )


def upgrade() -> None:
    _rewrite(f"user_id = (select {CURRENT})")


def downgrade() -> None:
    _rewrite(f"user_id = {CURRENT}")
