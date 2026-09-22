"""AI summary jobs and production media pipeline.

Revision ID: 20260901090000
Revises: 20260830090000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260901090000"
down_revision = "20260830090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    processing = postgresql.ENUM(
        "pending",
        "processing",
        "ready",
        "failed",
        name="media_processing_status",
        create_type=False,
    )
    review = postgresql.ENUM(
        "not_required",
        "required",
        "reviewed",
        name="media_review_status",
        create_type=False,
    )
    job_status = postgresql.ENUM(
        "pending",
        "processing",
        "completed",
        "failed",
        name="summary_generation_status",
        create_type=False,
    )
    for enum in (processing, review, job_status):
        enum.create(bind, checkfirst=True)

    op.add_column(
        "sources",
        sa.Column(
            "watermark_removal_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column(
        "sources", sa.Column("watermark_authorization_reference", sa.Text(), nullable=True)
    )
    op.add_column(
        "sources",
        sa.Column(
            "watermark_regions",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )

    for column in (
        sa.Column("display_object_key", sa.Text(), nullable=True),
        sa.Column("thumbnail_object_key", sa.Text(), nullable=True),
        sa.Column(
            "safety_signals",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("processing_status", processing, server_default="pending", nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("review_status", review, server_default="required", nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
    ):
        op.add_column("media", column)
    op.create_foreign_key(
        "fk_media_reviewed_by_user_id",
        "media",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "summary_generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", job_status, server_default="pending", nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_summary_generation_jobs"),
        sa.ForeignKeyConstraint(["record_id"], ["records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for name, columns in (
        ("ix_summary_generation_jobs_record_id", ["record_id"]),
        ("ix_summary_generation_jobs_requested_by_user_id", ["requested_by_user_id"]),
        ("ix_summary_generation_jobs_status", ["status"]),
        ("ix_summary_generation_jobs_input_hash", ["input_hash"]),
    ):
        op.create_index(name, "summary_generation_jobs", columns)

    additions = (
        sa.Column("model_provider", sa.String(50), server_default="openai", nullable=False),
        sa.Column("prompt_version", sa.String(100), server_default="summary-v1", nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("generation_job_id", sa.Uuid(), nullable=True),
    )
    for column in additions:
        op.add_column("summary_versions", column)
    op.create_foreign_key(
        "fk_summary_versions_generation_job_id",
        "summary_versions",
        "summary_generation_jobs",
        ["generation_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_summary_versions_input_hash", "summary_versions", ["input_hash"])
    op.create_index(
        "ix_summary_versions_generation_job_id", "summary_versions", ["generation_job_id"]
    )
    op.create_index(
        "uq_summary_versions_cache_key",
        "summary_versions",
        ["record_id", "input_hash", "model_name", "prompt_version"],
        unique=True,
        postgresql_where=sa.text("input_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_summary_versions_cache_key", table_name="summary_versions")
    op.drop_index("ix_summary_versions_generation_job_id", table_name="summary_versions")
    op.drop_index("ix_summary_versions_input_hash", table_name="summary_versions")
    op.drop_constraint(
        "fk_summary_versions_generation_job_id", "summary_versions", type_="foreignkey"
    )
    for name in (
        "generation_job_id",
        "cache_hit",
        "cached_input_tokens",
        "output_tokens",
        "input_tokens",
        "input_hash",
        "prompt_version",
        "model_provider",
    ):
        op.drop_column("summary_versions", name)
    op.drop_table("summary_generation_jobs")
    op.drop_constraint("fk_media_reviewed_by_user_id", "media", type_="foreignkey")
    for name in (
        "duration_seconds",
        "height",
        "width",
        "file_size_bytes",
        "reviewed_at",
        "reviewed_by_user_id",
        "review_notes",
        "review_status",
        "processing_error",
        "processing_status",
        "safety_signals",
        "thumbnail_object_key",
        "display_object_key",
    ):
        op.drop_column("media", name)
    for name in (
        "watermark_regions",
        "watermark_authorization_reference",
        "watermark_removal_enabled",
    ):
        op.drop_column("sources", name)
    bind = op.get_bind()
    for name in ("summary_generation_status", "media_review_status", "media_processing_status"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
