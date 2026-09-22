"""Operational consoles, notifications and priority jobs.

Revision ID: 20260904090000
Revises: 20260903090000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260904090000"
down_revision = "20260903090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_classifier_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(100), server_default="NudeNet", nullable=False),
        sa.Column(
            "model_version", sa.String(100), server_default="nudenet-3.4.2-320n", nullable=False
        ),
        sa.Column("safe_threshold", sa.Float(), server_default="0.20", nullable=False),
        sa.Column("explicit_threshold", sa.Float(), server_default="0.65", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_media_classifier_settings_singleton"),
        sa.CheckConstraint(
            "safe_threshold >= 0 AND explicit_threshold <= 1 "
            "AND safe_threshold < explicit_threshold",
            name="ck_media_classifier_thresholds",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO media_classifier_settings (id) VALUES (1)")
    op.create_table(
        "source_priority_recalculation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("previous_priority", sa.String(20), nullable=False),
        sa.Column("requested_priority", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("records_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("canonicals_changed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_priority_jobs_source", "source_priority_recalculation_jobs", ["source_id"]
    )
    op.create_index(
        "ix_source_priority_jobs_status", "source_priority_recalculation_jobs", ["status"]
    )
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("link", sa.String(500), nullable=True),
        sa.Column("audience", sa.String(20), server_default="operator", nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("dedup_key", sa.String(250), nullable=False),
        sa.Column(
            "details_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key"),
    )
    op.create_index("ix_notification_events_kind", "notification_events", ["kind"])
    op.create_index("ix_notification_events_created_at", "notification_events", ["created_at"])
    op.create_index("ix_notification_events_owner", "notification_events", ["owner_user_id"])
    op.create_table(
        "notification_reads",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notification_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id", "user_id"),
    )
    op.create_index("ix_notification_reads_user", "notification_reads", ["user_id"])


def downgrade() -> None:
    op.drop_table("notification_reads")
    op.drop_table("notification_events")
    op.drop_table("source_priority_recalculation_jobs")
    op.drop_table("media_classifier_settings")
