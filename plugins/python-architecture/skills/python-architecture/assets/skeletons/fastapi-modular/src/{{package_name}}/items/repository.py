"""Data access. The service depends on the Protocol, not on a concrete storage.

Swap InMemoryItemRepository for a SQLAlchemy implementation without touching
the service or the router.
"""

from dataclasses import replace
from typing import Protocol

from {{package_name}}.items.models import Item
from {{package_name}}.items.schemas import ItemCreate


class ItemRepository(Protocol):
    async def get(self, item_id: int) -> Item | None: ...
    async def list_all(self, *, offset: int, limit: int) -> list[Item]: ...
    async def add(self, data: ItemCreate) -> Item: ...
    async def save(self, item: Item) -> Item: ...
    async def delete(self, item_id: int) -> None: ...


class InMemoryItemRepository:
    def __init__(self) -> None:
        self._items: dict[int, Item] = {}
        self._next_id = 1

    async def get(self, item_id: int) -> Item | None:
        return self._items.get(item_id)

    async def list_all(self, *, offset: int, limit: int) -> list[Item]:
        return list(self._items.values())[offset : offset + limit]

    async def add(self, data: ItemCreate) -> Item:
        item = Item(id=self._next_id, **data.model_dump())
        self._items[item.id] = item
        self._next_id += 1
        return item

    async def save(self, item: Item) -> Item:
        self._items[item.id] = replace(item)
        return item

    async def delete(self, item_id: int) -> None:
        self._items.pop(item_id, None)
