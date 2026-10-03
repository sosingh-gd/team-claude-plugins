"""Business logic. No HTTP or storage details live here."""

from dataclasses import replace

from {{package_name}}.items.exceptions import ItemNotFoundError
from {{package_name}}.items.models import Item
from {{package_name}}.items.repository import ItemRepository
from {{package_name}}.items.schemas import ItemCreate, ItemUpdate


class ItemService:
    def __init__(self, repository: ItemRepository) -> None:
        self._repo = repository

    async def get(self, item_id: int) -> Item:
        item = await self._repo.get(item_id)
        if item is None:
            raise ItemNotFoundError(item_id)
        return item

    async def list_items(self, *, offset: int = 0, limit: int = 20) -> list[Item]:
        return await self._repo.list_all(offset=offset, limit=limit)

    async def create(self, data: ItemCreate) -> Item:
        return await self._repo.add(data)

    async def update(self, item_id: int, data: ItemUpdate) -> Item:
        item = await self.get(item_id)
        updated = replace(item, **data.model_dump(exclude_unset=True))
        return await self._repo.save(updated)

    async def delete(self, item_id: int) -> None:
        await self.get(item_id)
        await self._repo.delete(item_id)
