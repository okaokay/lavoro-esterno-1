"""Real exports, privacy erasure, and clear-phone authorization.

Revision ID: 20260902090000
Revises: 20260901090000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260902090000"
down_revision = "20260901090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "draft",
        "pending",
        "processing",
        "completed",
        "failed",
        name="erasure_request_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("can_view_clear_phone", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("export_jobs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column(
        "export_jobs", sa.Column("record_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "export_jobs",
        sa.Column(
            "estimated_uncompressed_bytes", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.add_column("export_jobs", sa.Column("archive_size_bytes", sa.BigInteger()))
    op.add_column(
        "export_jobs",
        sa.Column("include_clear_phone", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "export_job_records",
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["export_job_id"], ["export_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_id"], ["records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("export_job_id", "record_id"),
    )
    op.create_index("ix_export_job_records_record_id", "export_job_records", ["record_id"])

    op.create_table(
        "erasure_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_lookup_hash", sa.String(64), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", status, server_default="draft", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authorization_reference", sa.String(500), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "impact_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("result_json", postgresql.JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["record_id"], ["records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_erasure_requests_phone_lookup_hash", "erasure_requests", ["phone_lookup_hash"]
    )
    op.create_index("ix_erasure_requests_record_id", "erasure_requests", ["record_id"])
    op.create_index("ix_erasure_requests_status", "erasure_requests", ["status"])

    op.create_table(
        "suppression_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_lookup_hash", sa.String(64), nullable=False),
        sa.Column("erasure_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blocked_ingestions", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_blocked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["erasure_request_id"], ["erasure_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_lookup_hash"),
    )
    op.create_index(
        "ix_suppression_entries_phone_lookup_hash", "suppression_entries", ["phone_lookup_hash"]
    )


def downgrade() -> None:
    op.drop_table("suppression_entries")
    op.drop_table("erasure_requests")
    op.drop_table("export_job_records")
    for column in (
        "include_clear_phone",
        "archive_size_bytes",
        "estimated_uncompressed_bytes",
        "record_count",
        "started_at",
    ):
        op.drop_column("export_jobs", column)
    op.drop_column("users", "can_view_clear_phone")
    postgresql.ENUM(name="erasure_request_status").drop(op.get_bind(), checkfirst=True)
