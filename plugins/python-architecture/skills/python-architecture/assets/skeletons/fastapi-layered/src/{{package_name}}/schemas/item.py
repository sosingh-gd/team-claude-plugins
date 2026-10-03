"""API contract (request/response bodies). Kept separate from the domain/ORM model."""

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: float = Field(gt=0)


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    price: float | None = Field(default=None, gt=0)


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
