"""Multiprovider AI settings and provider-aware summary jobs.

Revision ID: 20260903090000
Revises: 20260902090000
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260903090000"
down_revision = "20260902090000"
branch_labels = None
depends_on = None

PROVIDERS = (
    ("ollama", "Ollama locale", "gemma4:e2b", True, "http://ollama:11434"),
    ("openai", "OpenAI", "gpt-5.6-luna", False, None),
    ("anthropic", "Anthropic / Claude", "", False, None),
    ("google", "Google Gemini", "", False, None),
    ("groq", "Groq", "", False, None),
    ("mistral", "Mistral", "", False, None),
    ("openrouter", "OpenRouter", "", False, None),
    ("custom_openai", "OpenAI-compatible personalizzato", "", False, None),
)


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("active_provider", sa.String(50), server_default="ollama", nullable=False),
        sa.Column("prompt_version", sa.String(100), server_default="summary-v1", nullable=False),
        sa.Column("user_daily_request_limit", sa.Integer(), server_default="20", nullable=False),
        sa.Column(
            "provider_requests_per_minute", sa.Integer(), server_default="10", nullable=False
        ),
        sa.Column("global_daily_token_budget", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_ai_settings_singleton"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_settings"),
    )
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200), server_default="", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "config_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_success", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_provider_configs"),
        sa.UniqueConstraint("provider", name="uq_ai_provider_configs_provider"),
    )
    op.create_index(
        "ix_ai_provider_configs_provider", "ai_provider_configs", ["provider"], unique=True
    )
    op.bulk_insert(
        sa.table(
            "ai_settings",
            sa.column("id", sa.Integer()),
            sa.column("active_provider", sa.String()),
            sa.column("prompt_version", sa.String()),
            sa.column("user_daily_request_limit", sa.Integer()),
            sa.column("provider_requests_per_minute", sa.Integer()),
            sa.column("global_daily_token_budget", sa.BigInteger()),
            sa.column("revision", sa.Integer()),
        ),
        [
            {
                "id": 1,
                "active_provider": "ollama",
                "prompt_version": "summary-v1",
                "user_daily_request_limit": 20,
                "provider_requests_per_minute": 10,
                "global_daily_token_budget": 0,
                "revision": 1,
            }
        ],
    )
    provider_table = sa.table(
        "ai_provider_configs",
        sa.column("id", sa.Uuid()),
        sa.column("provider", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("model_name", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("base_url", sa.String()),
        sa.column("config_json", postgresql.JSONB()),
        sa.column("revision", sa.Integer()),
    )
    op.bulk_insert(
        provider_table,
        [
            {
                "id": uuid.uuid4(),
                "provider": provider,
                "display_name": label,
                "model_name": model,
                "enabled": enabled,
                "base_url": url,
                "config_json": {},
                "revision": 1,
            }
            for provider, label, model, enabled, url in PROVIDERS
        ],
    )
    op.add_column(
        "summary_generation_jobs",
        sa.Column("model_provider", sa.String(50), server_default="openai", nullable=False),
    )
    op.add_column(
        "summary_generation_jobs",
        sa.Column("provider_config_revision", sa.Integer(), nullable=True),
    )
    op.drop_index("uq_summary_versions_cache_key", table_name="summary_versions")
    op.create_index(
        "uq_summary_versions_cache_key",
        "summary_versions",
        ["record_id", "input_hash", "model_provider", "model_name", "prompt_version"],
        unique=True,
        postgresql_where=sa.text("input_hash IS NOT NULL"),
    )
    op.execute(
        "UPDATE summary_generation_jobs SET status='failed', "
        "error_message='Configurazione AI aggiornata: rilanciare il job.', "
        "completed_at=now() WHERE status IN ('pending','processing')"
    )


def downgrade() -> None:
    op.drop_index("uq_summary_versions_cache_key", table_name="summary_versions")
    op.create_index(
        "uq_summary_versions_cache_key",
        "summary_versions",
        ["record_id", "input_hash", "model_name", "prompt_version"],
        unique=True,
        postgresql_where=sa.text("input_hash IS NOT NULL"),
    )
    op.drop_column("summary_generation_jobs", "provider_config_revision")
    op.drop_column("summary_generation_jobs", "model_provider")
    op.drop_index("ix_ai_provider_configs_provider", table_name="ai_provider_configs")
    op.drop_table("ai_provider_configs")
    op.drop_table("ai_settings")
