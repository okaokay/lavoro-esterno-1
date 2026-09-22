"""Persist safe scraper pagination diagnostics."""

import sqlalchemy as sa
from alembic import op

revision = "20260908100000"
down_revision = "20260907120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_runs",
        sa.Column("pages_visited", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("pagination_mode", sa.String(length=20), server_default="none", nullable=False),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("pagination_stop_reason", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scrape_runs", "pagination_stop_reason")
    op.drop_column("scrape_runs", "pagination_mode")
    op.drop_column("scrape_runs", "pages_visited")
