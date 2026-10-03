"""HTTP layer: parse input, call the service, shape the response. Nothing else."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from {{package_name}}.items.dependencies import ItemServiceDep
from {{package_name}}.items.schemas import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
async def list_items(
    service: ItemServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ItemRead]:
    items = await service.list_items(offset=offset, limit=limit)
    return [ItemRead.model_validate(item) for item in items]


@router.get("/{item_id}")
async def get_item(item_id: int, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(await service.get(item_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(await service.create(data))


@router.patch("/{item_id}")
async def update_item(item_id: int, data: ItemUpdate, service: ItemServiceDep) -> ItemRead:
    return ItemRead.model_validate(await service.update(item_id, data))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, service: ItemServiceDep) -> None:
    await service.delete(item_id)
