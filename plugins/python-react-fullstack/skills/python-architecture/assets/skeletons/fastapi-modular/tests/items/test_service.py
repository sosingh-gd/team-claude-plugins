"""Service tests run without HTTP: the payoff of keeping routers thin."""

import pytest

from {{package_name}}.items.exceptions import ItemNotFoundError
from {{package_name}}.items.repository import ItemRepository
from {{package_name}}.items.schemas import ItemCreate, ItemUpdate
from {{package_name}}.items.service import ItemService


@pytest.fixture
def service() -> ItemService:
    return ItemService(ItemRepository())


async def test_create_and_get(service: ItemService) -> None:
    created = await service.create(ItemCreate(name="Widget", price=9.5))
    assert (await service.get(created.id)).name == "Widget"


async def test_update_only_changes_given_fields(service: ItemService) -> None:
    created = await service.create(ItemCreate(name="Widget", price=9.5, description="d"))
    updated = await service.update(created.id, ItemUpdate(price=12.0))
    assert updated.price == 12.0
    assert updated.description == "d"


async def test_get_missing_raises(service: ItemService) -> None:
    with pytest.raises(ItemNotFoundError):
        await service.get(999)


async def test_delete(service: ItemService) -> None:
    created = await service.create(ItemCreate(name="Widget", price=1.0))
    await service.delete(created.id)
    assert await service.list_items() == []
