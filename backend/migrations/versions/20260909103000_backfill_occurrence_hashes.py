"""Backfill deterministic hashes for installations upgraded before the data pass.

Revision ID: 20260909103000
Revises: 20260909100000
"""

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909103000"
down_revision: str | None = "20260909100000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE advertisements SET last_changed_at="
            "COALESCE(scraped_at, first_seen_at, now())"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE media m SET last_seen_at=COALESCE(a.last_seen_at, m.created_at, now()) "
            "FROM advertisements a WHERE a.id=m.advertisement_id"
        )
    )
    advertisements = bind.execute(
        sa.text("SELECT id, title, description, custom_fields, content_hash FROM advertisements")
    ).mappings()
    for advertisement in advertisements:
        hashes = list(
            bind.execute(
                sa.text("SELECT sha256 FROM media WHERE advertisement_id=:id ORDER BY sha256"),
                {"id": advertisement["id"]},
            ).scalars()
        )
        media_hash = hashlib.sha256(
            json.dumps(sorted(set(hashes)), separators=(",", ":")).encode()
        ).hexdigest()
        content_hash = advertisement["content_hash"]
        if not content_hash:
            payload = json.dumps(
                {
                    "title": advertisement["title"] or "",
                    "description": advertisement["description"] or "",
                    "custom_fields": advertisement["custom_fields"] or {},
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content_hash = hashlib.sha256(payload.encode()).hexdigest()
        fingerprint = hashlib.sha256(f"{content_hash}:{media_hash}".encode()).hexdigest()
        bind.execute(
            sa.text(
                "UPDATE advertisements SET content_hash=:content, "
                "media_set_hash=:media WHERE id=:id"
            ),
            {"id": advertisement["id"], "content": content_hash, "media": media_hash},
        )
        bind.execute(
            sa.text(
                "UPDATE advertisement_versions SET content_hash=:content, "
                "media_set_hash=:media, fingerprint=:fingerprint "
                "WHERE advertisement_id=:id AND revision=1"
            ),
            {
                "id": advertisement["id"],
                "content": content_hash,
                "media": media_hash,
                "fingerprint": fingerprint,
            },
        )


def downgrade() -> None:
    # Data-only normalization; retaining deterministic values is safe.
    pass
