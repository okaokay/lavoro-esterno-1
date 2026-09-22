"""Pipeline batches, source countries, proxy feeds and webhook outbox.

Revision ID: 20260917090000
Revises: 20260909110000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917090000"
down_revision: str | None = "20260909110000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("country_code", sa.String(2), nullable=True))
    op.create_index("ix_sources_country_code", "sources", ["country_code"])
    op.add_column("advertisements", sa.Column("listing_page_number", sa.Integer(), nullable=True))
    op.add_column(
        "advertisements", sa.Column("original_content_encrypted", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "advertisements",
        sa.Column(
            "sanitization_metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_advertisements_listing_page_number", "advertisements", ["listing_page_number"]
    )

    op.create_table(
        "ingestion_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publish_batch_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="ck_ingestion_settings_singleton"),
    )
    op.execute(
        "INSERT INTO ingestion_settings (id, publish_batch_size, revision) VALUES (1, 50, 1)"
    )

    op.create_table(
        "proxy_feeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), unique=True, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("scheme", sa.String(10), nullable=False),
        sa.Column(
            "pool_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proxy_pools.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("headers_encrypted", sa.LargeBinary()),
        sa.Column(
            "header_names",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("next_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_status", sa.String(30)),
        sa.Column("last_sync_message", sa.String(500)),
        sa.Column("last_imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_proxy_feeds_pool_id", "proxy_feeds", ["pool_id"])
    op.create_index("ix_proxy_feeds_next_sync_at", "proxy_feeds", ["next_sync_at"])
    op.add_column(
        "proxy_endpoints",
        sa.Column(
            "managed_by_feed_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("proxy_feeds.id", ondelete="SET NULL"),
        ),
    )
    op.create_index(
        "ix_proxy_endpoints_managed_by_feed_id", "proxy_endpoints", ["managed_by_feed_id"]
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), unique=True, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("all_sources", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("phone_policy", sa.String(20), nullable=False, server_default="masked"),
        sa.Column("secret_encrypted", sa.LargeBinary()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "webhook_endpoint_sources",
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "scrape_run_payloads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scrape_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_runs.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("payload_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_scrape_run_payloads_scrape_run_id", "scrape_run_payloads", ["scrape_run_id"]
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scrape_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scrape_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_http_status", sa.Integer()),
        sa.Column("last_error", sa.String(200)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "endpoint_id", "scrape_run_id", name="uq_webhook_delivery_endpoint_run"
        ),
    )
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_scrape_run_id", "webhook_deliveries", ["scrape_run_id"])
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index(
        "ix_webhook_deliveries_next_attempt_at", "webhook_deliveries", ["next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("scrape_run_payloads")
    op.drop_table("webhook_endpoint_sources")
    op.drop_table("webhook_endpoints")
    op.drop_index("ix_proxy_endpoints_managed_by_feed_id", table_name="proxy_endpoints")
    op.drop_column("proxy_endpoints", "managed_by_feed_id")
    op.drop_table("proxy_feeds")
    op.drop_table("ingestion_settings")
    op.drop_index("ix_advertisements_listing_page_number", table_name="advertisements")
    op.drop_column("advertisements", "sanitization_metadata")
    op.drop_column("advertisements", "original_content_encrypted")
    op.drop_column("advertisements", "listing_page_number")
    op.drop_index("ix_sources_country_code", table_name="sources")
    op.drop_column("sources", "country_code")
