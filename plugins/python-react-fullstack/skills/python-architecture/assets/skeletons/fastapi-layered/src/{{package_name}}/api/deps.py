"""Shared FastAPI dependencies. Tests override these via app.dependency_overrides."""

from typing import Annotated

from fastapi import Depends

from {{package_name}}.repositories.item import InMemoryItemRepository, ItemRepository
from {{package_name}}.services.item import ItemService

# Process-wide store for the in-memory example. With a database, this becomes a
# repository built from a per-request session dependency instead.
_repository = InMemoryItemRepository()


def get_item_repository() -> ItemRepository:
    return _repository


def get_item_service(
    repository: Annotated[ItemRepository, Depends(get_item_repository)],
) -> ItemService:
    return ItemService(repository)


ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]
