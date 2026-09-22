"""Persist arbitrary configured scraper fields on advertisements."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260907120000"
down_revision = "20260904150000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "advertisements",
        sa.Column(
            "custom_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("advertisements", "custom_fields")
