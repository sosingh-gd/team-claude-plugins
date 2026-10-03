"""Application factory and ASGI entrypoint (`uvicorn {{package_name}}.main:app`)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from {{package_name}}.api import api_router
from {{package_name}}.config import get_settings
from {{package_name}}.exceptions import register_exception_handlers
from {{package_name}}.health.router import router as health_router
from {{package_name}}.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create shared resources (DB engine, HTTP clients) on startup, close them on shutdown."""
    settings = get_settings()
    logger.info("Starting %s in %s mode", settings.app_name, settings.environment)
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    is_prod = settings.environment == "production"
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
