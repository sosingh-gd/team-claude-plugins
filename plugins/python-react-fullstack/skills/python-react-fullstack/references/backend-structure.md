# Backend Structure (FastAPI)

## Contents
1. Layout and layer responsibilities
2. App factory (`main.py`)
3. Settings
4. The `ApiModel` base and schemas
5. Database session and dependencies
6. Router → service → repository example
7. Domain errors
8. Testing

## 1. Layout and layer responsibilities

```
backend/app/
├── main.py                 # create_app(); no import-time side effects (no DB connect)
├── core/
│   ├── config.py           # Settings (pydantic-settings)
│   ├── errors.py           # AppError hierarchy, ProblemDetail, exception handlers
│   ├── schemas.py          # ApiModel base, CursorPage/OffsetPage generics
│   ├── security.py         # auth helpers (see auth.md)
│   └── logging.py
├── db/
│   ├── base.py             # DeclarativeBase
│   └── session.py          # engine + async_sessionmaker, created in lifespan
├── api/
│   ├── deps.py             # shared Annotated dependencies (SessionDep, CurrentUser)
│   └── v1/router.py        # APIRouter(prefix="/api/v1"), includes feature routers
├── features/
│   └── orders/
│       ├── router.py       # HTTP only
│       ├── schemas.py      # OrderCreate / OrderUpdate / OrderRead — the contract
│       ├── service.py      # business rules; no FastAPI imports
│       ├── repository.py   # SQLAlchemy queries
│       ├── models.py       # ORM models
│       └── deps.py         # OrderServiceDep wiring
└── scripts/export_openapi.py
```

| Layer | Knows about | Must not |
|---|---|---|
| `router.py` | FastAPI, schemas, service | contain business rules or SQL |
| `service.py` | repositories, schemas or domain types, `core.errors` | import FastAPI, `Request`, `HTTPException` |
| `repository.py` | SQLAlchemy models, session | know about HTTP or schemas' camelCase |
| `schemas.py` | Pydantic, `ApiModel` | import ORM models (use `from_attributes` instead) |

Features import each other only through their service (never another feature's repository or models). Cross-cutting needs go in `core/`.

## 2. App factory

```python
# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.session import dispose_engine, init_engine


def operation_id(route: APIRoute) -> str:
    # Function names become operationIds: list_orders -> listOrders in codegen.
    # Keep endpoint function names unique across the app.
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine(get_settings().database_url)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        generate_unique_id_function=operation_id,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    register_exception_handlers(app)
    if settings.cors_origins:  # only for cross-origin deployments, see dev-setup.md
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(api_router)
    return app


app = create_app()
```

Keep `create_app()` free of network calls so `export_openapi.py` and tests can import it without a database.

## 3. Settings

```python
# app/core/config.py
from functools import lru_cache
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    app_name: str = "My App"
    version: str = "0.1.0"
    environment: str = "local"           # local | staging | production
    database_url: PostgresDsn
    cors_origins: list[str] = []          # empty = same-origin deployment
    session_cookie_secure: bool = True
    secret_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Never read `os.environ` elsewhere. Frontend config is separate (`VITE_*` vars in `frontend/src/config`) and must never contain secrets.

## 4. The `ApiModel` base and schemas

```python
# app/core/schemas.py
from typing import Generic, TypeVar  # or PEP 695: class CursorPage[T](ApiModel) on 3.12+
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for every request/response schema: camelCase JSON, snake_case Python."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,     # Pydantic >= 2.11; use populate_by_name=True on older versions
        validate_by_alias=True,
        from_attributes=True,      # allows OrderRead.model_validate(orm_obj)
        # Response fields with defaults are always present in output, so mark them required in the
        # serialization schema. Without this, TS gets `type?: "text_delta"` and discriminated unions
        # (SSE events, status unions) stop narrowing. Request schemas are unaffected.
        json_schema_serialization_defaults_required=True,
    )


class CursorPage(ApiModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class OffsetPage(ApiModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

FastAPI serializes `response_model` output by alias by default, and parses request bodies by alias, so this one base gives camelCase in both directions.

```python
# app/features/orders/schemas.py
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field
from app.core.schemas import ApiModel


class OrderStatus(StrEnum):
    draft = "draft"
    submitted = "submitted"
    cancelled = "cancelled"


class OrderLineIn(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=1000)


class OrderCreate(ApiModel):
    customer_id: UUID
    lines: list[OrderLineIn] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)


class OrderUpdate(ApiModel):
    # PATCH: every field optional; apply with model_dump(exclude_unset=True)
    note: str | None = None
    status: OrderStatus | None = None


class OrderRead(ApiModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total: Decimal = Field(description="Decimal serialized as string")
    note: str | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
```

## 5. Database session and dependencies

```python
# app/db/session.py
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(str(url), pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    assert _sessionmaker is not None, "engine not initialised"
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def session_factory() -> async_sessionmaker[AsyncSession]:
    """For code that outlives a request (streams, background jobs)."""
    assert _sessionmaker is not None
    return _sessionmaker
```

```python
# app/api/deps.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
# CurrentUser is defined in core/security.py, see auth.md
```

## 6. Router → service → repository

```python
# app/features/orders/repository.py
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Order


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, order_id: UUID) -> Order | None:
        return await self.session.get(Order, order_id)

    async def list_after(self, cursor: UUID | None, limit: int) -> list[Order]:
        stmt = select(Order).order_by(Order.id).limit(limit + 1)
        if cursor:
            stmt = stmt.where(Order.id > cursor)
        return list((await self.session.scalars(stmt)).all())

    async def add(self, order: Order) -> Order:
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order
```

```python
# app/features/orders/service.py
from uuid import UUID
from app.core.errors import ConflictError, NotFoundError
from app.core.schemas import CursorPage
from .repository import OrderRepository
from .schemas import OrderCreate, OrderRead, OrderUpdate, OrderStatus


class OrderService:
    def __init__(self, repo: OrderRepository) -> None:
        self.repo = repo

    async def get(self, order_id: UUID) -> OrderRead:
        order = await self.repo.get(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        return OrderRead.model_validate(order)

    async def list(self, cursor: UUID | None, limit: int) -> CursorPage[OrderRead]:
        rows = await self.repo.list_after(cursor, limit)
        has_more = len(rows) > limit
        rows = rows[:limit]
        return CursorPage[OrderRead](
            items=[OrderRead.model_validate(r) for r in rows],
            next_cursor=str(rows[-1].id) if has_more else None,
        )

    async def update(self, order_id: UUID, data: OrderUpdate) -> OrderRead:
        order = await self.repo.get(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        if order.status == OrderStatus.cancelled:
            raise ConflictError("Cancelled orders cannot be changed", code="order_cancelled")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(order, field, value)
        return OrderRead.model_validate(order)

    # create() and delete() follow the same pattern: validate rules, call repo, return schema / None.
```

```python
# app/features/orders/deps.py
from typing import Annotated
from fastapi import Depends
from app.api.deps import SessionDep
from .repository import OrderRepository
from .service import OrderService


def get_order_service(session: SessionDep) -> OrderService:
    return OrderService(OrderRepository(session))

OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
```

```python
# app/features/orders/router.py
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query, status
from app.core.schemas import CursorPage
from .deps import OrderServiceDep
from .schemas import OrderCreate, OrderRead, OrderUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=CursorPage[OrderRead])
async def list_orders(
    service: OrderServiceDep,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return await service.list(cursor, limit)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(order_id: UUID, service: OrderServiceDep):
    return await service.get(order_id)


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(body: OrderCreate, service: OrderServiceDep):
    return await service.create(body)


@router.patch("/{order_id}", response_model=OrderRead)
async def update_order(order_id: UUID, body: OrderUpdate, service: OrderServiceDep):
    return await service.update(order_id, body)


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: UUID, service: OrderServiceDep) -> None:
    await service.delete(order_id)
```

Multi-word query params need an explicit alias to stay camelCase: `page_size: Annotated[int, Query(alias="pageSize")] = 20`, or group them in an `ApiModel` and declare `params: Annotated[ListParams, Query()]`.

```python
# app/api/v1/router.py
from fastapi import APIRouter
from app.core.errors import COMMON_ERROR_RESPONSES
from app.features.orders.router import router as orders_router

api_router = APIRouter(prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)
api_router.include_router(orders_router)
```

## 7. Domain errors

Defined in `core/errors.py` (full handler code in `api-contract.md`). Services raise these; handlers turn them into Problem Details:

```python
class AppError(Exception):
    status = 500
    code = "internal_error"
    title = "Internal Server Error"

    def __init__(self, detail: str | None = None, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code

class NotFoundError(AppError):        status, code, title = 404, "not_found", "Not Found"
class ConflictError(AppError):        status, code, title = 409, "conflict", "Conflict"
class PermissionDeniedError(AppError): status, code, title = 403, "forbidden", "Forbidden"
class UnauthenticatedError(AppError): status, code, title = 401, "unauthenticated", "Unauthenticated"
class BusinessRuleError(AppError):    status, code, title = 422, "business_rule", "Unprocessable Content"
```

## 8. Testing

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import create_app


@pytest.fixture
async def client(test_db):  # test_db: fixture that inits engine on a test database / transaction
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_get_missing_order_returns_problem(client):
    r = await client.get("/api/v1/orders/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "not_found"


async def test_create_validates_camel_case_fields(client):
    r = await client.post("/api/v1/orders", json={"customerId": "not-a-uuid", "lines": []})
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["errors"]}
    assert {"customerId", "lines"} <= fields
```

Test through HTTP with camelCase payloads: this tests the contract the frontend actually sees. Unit-test services directly for complex business rules. Override dependencies with `app.dependency_overrides[get_current_user] = ...` for auth.
