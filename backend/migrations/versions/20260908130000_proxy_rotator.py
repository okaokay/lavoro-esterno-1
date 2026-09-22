"""Add global proxy pools, endpoint health and scraper attempt history."""

import sqlalchemy as sa
from alembic import op

revision = "20260908130000"
down_revision = "20260908100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proxy_pools",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "proxy_endpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scheme", sa.String(10), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("credentials_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scheme IN ('http','https','socks4','socks5')", name="ck_proxy_scheme"),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_proxy_port"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "proxy_pool_members",
        sa.Column("pool_id", sa.Uuid(), nullable=False),
        sa.Column("proxy_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["proxy_pools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proxy_id"], ["proxy_endpoints.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("pool_id", "proxy_id"),
    )
    op.add_column("sources", sa.Column("proxy_pool_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_sources_proxy_pool_id",
        "sources",
        "proxy_pools",
        ["proxy_pool_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sources_proxy_pool_id", "sources", ["proxy_pool_id"])
    op.add_column(
        "scrape_runs",
        sa.Column("proxy_attempts_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "scrape_runs",
        sa.Column("proxy_rotations_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("scrape_runs", sa.Column("proxy_stop_reason", sa.String(50), nullable=True))
    op.create_table(
        "scrape_run_proxy_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scrape_run_id", sa.Uuid(), nullable=False),
        sa.Column("proxy_endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("failure_category", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["scrape_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proxy_endpoint_id"], ["proxy_endpoints.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scrape_run_id", "attempt_number", name="uq_proxy_attempt_run_number"),
    )
    op.create_index("ix_proxy_attempt_run", "scrape_run_proxy_attempts", ["scrape_run_id"])
    op.create_index("ix_proxy_attempt_endpoint", "scrape_run_proxy_attempts", ["proxy_endpoint_id"])
    op.execute(
        "UPDATE sources SET scrape_config = scrape_config - 'proxy' WHERE scrape_config ? 'proxy'"
    )


def downgrade() -> None:
    op.drop_table("scrape_run_proxy_attempts")
    op.drop_column("scrape_runs", "proxy_stop_reason")
    op.drop_column("scrape_runs", "proxy_rotations_count")
    op.drop_column("scrape_runs", "proxy_attempts_count")
    op.drop_index("ix_sources_proxy_pool_id", table_name="sources")
    op.drop_constraint("fk_sources_proxy_pool_id", "sources", type_="foreignkey")
    op.drop_column("sources", "proxy_pool_id")
    op.drop_table("proxy_pool_members")
    op.drop_table("proxy_endpoints")
    op.drop_table("proxy_pools")
