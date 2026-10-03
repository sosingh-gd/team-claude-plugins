from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{package_name}}.items.dependencies import get_item_repository
from {{package_name}}.items.repository import InMemoryItemRepository
from {{package_name}}.main import create_app


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    repository = InMemoryItemRepository()  # fresh, isolated state per test
    application.dependency_overrides[get_item_repository] = lambda: repository
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
