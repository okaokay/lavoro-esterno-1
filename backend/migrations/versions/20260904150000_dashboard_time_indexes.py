"""Indexes for bounded dashboard time queries.

Revision ID: 20260904150000
Revises: 20260904090000
"""

from alembic import op

revision = "20260904150000"
down_revision = "20260904090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_records_created_at", "records", ["created_at"])
    op.create_index("ix_scrape_runs_started_at", "scrape_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_scrape_runs_started_at", table_name="scrape_runs")
    op.drop_index("ix_records_created_at", table_name="records")
