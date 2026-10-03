"""Aggregates the versioned feature routers. Add new modules here."""

from fastapi import APIRouter

from {{package_name}}.items.router import router as items_router

api_router = APIRouter()
api_router.include_router(items_router)
