"""Aggrega tutti i router v1 sotto i rispettivi prefissi."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    ai_settings,
    auth,
    dashboard,
    exports,
    integrations,
    media,
    operations,
    privacy,
    proxies,
    records,
    search,
    sources,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(records.router, prefix="/records", tags=["records"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(ai_settings.router, prefix="/admin", tags=["ai-settings"])
api_router.include_router(proxies.router, prefix="/admin", tags=["proxy-settings"])
api_router.include_router(integrations.router, prefix="/admin", tags=["integrations"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(privacy.router, prefix="/privacy", tags=["privacy"])
api_router.include_router(operations.router, tags=["operations"])
