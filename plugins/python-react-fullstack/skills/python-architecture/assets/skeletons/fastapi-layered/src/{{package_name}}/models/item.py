"""Domain model. Replace with a SQLAlchemy model once a database is added."""

from dataclasses import dataclass


@dataclass(slots=True)
class Item:
    id: int
    name: str
    price: float
    description: str | None = None
