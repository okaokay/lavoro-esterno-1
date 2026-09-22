"""Add fixed-delay automatic source scraping and persistent pending runs."""

import sqlalchemy as sa
from alembic import op

revision = "20260908160000"
down_revision = "20260908130000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE scrape_run_status ADD VALUE IF NOT EXISTS 'pending' BEFORE 'running'"
        )

    op.add_column(
        "sources",
        sa.Column(
            "automatic_scraping_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column("sources", sa.Column("scrape_interval_minutes", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("next_scrape_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sources", sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "sources", sa.Column("last_completed_scrape_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("sources", sa.Column("last_schedule_skip_reason", sa.String(80), nullable=True))
    op.add_column(
        "sources", sa.Column("schedule_revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_check_constraint(
        "ck_source_scrape_interval",
        "sources",
        "scrape_interval_minutes IS NULL OR scrape_interval_minutes BETWEEN 15 AND 43200",
    )
    op.create_index("ix_sources_next_scrape_at", "sources", ["next_scrape_at"])

    op.alter_column(
        "scrape_runs", "started_at", existing_type=sa.DateTime(timezone=True), nullable=True
    )
    op.add_column(
        "scrape_runs",
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("trigger_type", sa.String(20), server_default="manual", nullable=False),
    )
    op.add_column("scrape_runs", sa.Column("scheduled_for", sa.DateTime(timezone=True)))
    op.add_column("scrape_runs", sa.Column("celery_task_id", sa.String(100)))
    op.create_check_constraint(
        "ck_scrape_run_trigger_type", "scrape_runs", "trigger_type IN ('manual','scheduled')"
    )
    op.create_index(
        "uq_scrape_run_source_active",
        "scrape_runs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','running')"),
    )
    op.create_index(
        "uq_scrape_runs_celery_task_id",
        "scrape_runs",
        ["celery_task_id"],
        unique=True,
        postgresql_where=sa.text("celery_task_id IS NOT NULL"),
    )
    op.create_index("ix_scrape_runs_queued_at", "scrape_runs", ["queued_at"])


def downgrade() -> None:
    op.execute(
        "UPDATE scrape_runs SET status='failed', "
        "started_at=COALESCE(started_at, queued_at), "
        "finished_at=COALESCE(finished_at, now()) WHERE status='pending'"
    )
    op.drop_index("ix_scrape_runs_queued_at", table_name="scrape_runs")
    op.drop_index("uq_scrape_runs_celery_task_id", table_name="scrape_runs")
    op.drop_index("uq_scrape_run_source_active", table_name="scrape_runs")
    op.drop_constraint("ck_scrape_run_trigger_type", "scrape_runs", type_="check")
    op.drop_column("scrape_runs", "celery_task_id")
    op.drop_column("scrape_runs", "scheduled_for")
    op.drop_column("scrape_runs", "trigger_type")
    op.drop_column("scrape_runs", "queued_at")
    op.alter_column(
        "scrape_runs", "started_at", existing_type=sa.DateTime(timezone=True), nullable=False
    )

    op.drop_index("ix_sources_next_scrape_at", table_name="sources")
    op.drop_constraint("ck_source_scrape_interval", "sources", type_="check")
    op.drop_column("sources", "schedule_revision")
    op.drop_column("sources", "last_schedule_skip_reason")
    op.drop_column("sources", "last_completed_scrape_at")
    op.drop_column("sources", "last_scheduled_at")
    op.drop_column("sources", "next_scrape_at")
    op.drop_column("sources", "scrape_interval_minutes")
    op.drop_column("sources", "automatic_scraping_enabled")
    # PostgreSQL enum values are intentionally retained on downgrade.
