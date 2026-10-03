"""Aggregates the v1 routers. Add new resource routers here."""

from fastapi import APIRouter

from {{package_name}}.api.v1.items import router as items_router

api_router = APIRouter()
api_router.include_router(items_router)
