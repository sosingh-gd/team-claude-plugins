"""Data access for items. Kept in memory so the skeleton runs without a database.

To use a database, rewrite this class with SQLAlchemy and keep its method names;
the service and router don't change.
"""

from dataclasses import replace

from {{package_name}}.models.item import Item
from {{package_name}}.schemas.item import ItemCreate


class ItemRepository:
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
