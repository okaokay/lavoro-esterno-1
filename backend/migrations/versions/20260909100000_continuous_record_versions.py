"""Continuous material-change tracking for scraped occurrences.

Revision ID: 20260909100000
Revises: 20260908160000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260909100000"
down_revision: str | None = "20260908160000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "records", sa.Column("content_revision", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("advertisements", sa.Column("media_set_hash", sa.String(64), nullable=True))
    op.add_column(
        "advertisements", sa.Column("revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "advertisements",
        sa.Column(
            "last_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_advertisements_media_set_hash", "advertisements", ["media_set_hash"])
    op.create_unique_constraint(
        "uq_advertisements_occurrence",
        "advertisements",
        ["record_id", "source_id", "source_url"],
    )
    op.add_column(
        "media", sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "media",
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_media_is_current", "media", ["is_current"])
    op.execute(
        "UPDATE advertisements SET last_changed_at = COALESCE(scraped_at, first_seen_at, now())"
    )
    op.execute(
        """
        UPDATE media m SET last_seen_at = COALESCE(a.last_seen_at, m.created_at, now())
        FROM advertisements a WHERE a.id = m.advertisement_id
        """
    )
    op.add_column(
        "scrape_runs", sa.Column("items_updated", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "scrape_runs",
        sa.Column("items_unchanged", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "summary_versions",
        sa.Column("record_content_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "summary_generation_jobs",
        sa.Column("record_content_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "advertisement_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("advertisement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("scrape_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("media_set_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["advertisement_id"], ["advertisements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "advertisement_id", "revision", name="uq_advertisement_versions_revision"
        ),
    )
    op.create_index(
        "ix_advertisement_versions_advertisement_id", "advertisement_versions", ["advertisement_id"]
    )
    op.create_index(
        "ix_advertisement_versions_scrape_run_id", "advertisement_versions", ["scrape_run_id"]
    )
    op.create_index(
        "ix_advertisement_versions_fingerprint", "advertisement_versions", ["fingerprint"]
    )

    # Existing rows become revision 1. Hashes left unknown are derived from the
    # current media set by the first comparison, preventing destructive guesses.
    op.execute(
        """
        INSERT INTO advertisement_versions (
            id, advertisement_id, revision, content_hash, media_set_hash,
            fingerprint, changed_fields, snapshot_json, created_at
        )
        SELECT gen_random_uuid(), a.id, 1,
               COALESCE(a.content_hash, repeat('0', 64)),
               repeat('0', 64), repeat('0', 64), '[\"initial\"]'::jsonb,
               jsonb_build_object(
                   'title', a.title,
                   'description', a.description,
                   'customFields', COALESCE(a.custom_fields, '{}'::jsonb),
                   'mediaHashes', COALESCE((
                       SELECT jsonb_agg(m.sha256 ORDER BY m.sha256)
                       FROM media m WHERE m.advertisement_id = a.id
                   ), '[]'::jsonb)
               ),
               COALESCE(a.first_seen_at, now())
        FROM advertisements a
        """
    )
def downgrade() -> None:
    op.drop_table("advertisement_versions")
    op.drop_column("summary_generation_jobs", "record_content_revision")
    op.drop_column("summary_versions", "record_content_revision")
    op.drop_column("scrape_runs", "items_unchanged")
    op.drop_column("scrape_runs", "items_updated")
    op.drop_index("ix_media_is_current", table_name="media")
    op.drop_column("media", "last_seen_at")
    op.drop_column("media", "is_current")
    op.drop_constraint("uq_advertisements_occurrence", "advertisements", type_="unique")
    op.drop_index("ix_advertisements_media_set_hash", table_name="advertisements")
    op.drop_column("advertisements", "last_changed_at")
    op.drop_column("advertisements", "revision")
    op.drop_column("advertisements", "media_set_hash")
    op.drop_column("records", "content_revision")
