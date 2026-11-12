from collections.abc import Sequence

from alembic import op

revision: str = "0029_wallpaper_variants"
down_revision: str | None = "0028_events_listed_and_figures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VARIANTS = r"variant in ('image', 'blurred') or variant ~ '^(avif|webp)-[0-9]{2,4}$'"


def upgrade() -> None:
    op.drop_constraint("ui_wallpapers_variant", "ui_wallpapers", schema="kernel")
    op.create_check_constraint("ui_wallpapers_variant", "ui_wallpapers", VARIANTS, schema="kernel")


def downgrade() -> None:
    op.execute("delete from kernel.ui_wallpapers where variant not in ('image', 'blurred')")
    op.drop_constraint("ui_wallpapers_variant", "ui_wallpapers", schema="kernel")
    op.create_check_constraint(
        "ui_wallpapers_variant", "ui_wallpapers", "variant in ('image', 'blurred')", schema="kernel"
    )
