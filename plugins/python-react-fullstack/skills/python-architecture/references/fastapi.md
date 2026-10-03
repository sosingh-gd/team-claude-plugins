# FastAPI reference

Contents: choosing a layout · layering rules · dependency injection · settings · database (async SQLAlchemy + Alembic) · errors · schemas · async correctness · testing · security · observability · scaling · checklist for adding a feature

## Choosing a layout

| Layout | Use when | Cost |
|---|---|---|
| **Layered** (`api/`, `schemas/`, `services/`, `repositories/`, `models/`) | Small service, one or two domains, a handful of endpoints | Features scatter across folders as the app grows |
| **Modular / domain-based** (`orders/`, `users/`, each with router, schemas, service, repository, models) | Default for anything expected to grow or have several developers | Slightly more files per feature |
| **Clean / hexagonal** (`domain/`, `application/`, `infrastructure/`, `presentation/`) | Complex business rules, long-lived core, must test logic without DB/framework | Mapping boilerplate between ORM, domain entities and schemas |

The scaffold supports layered and modular (`--layout`). For hexagonal, start from modular and inside each module split into:

```
orders/
├── domain/          # entities, value objects, domain services: pure Python, no FastAPI/SQLAlchemy imports
├── application/     # use cases + repository Protocols (ports)
├── infrastructure/  # SQLAlchemy models + repository implementations (adapters)
└── api/             # router, request/response schemas, dependencies
```

The rule that makes hexagonal worth it: dependencies point inward. `domain` imports nothing from the other layers; `infrastructure` and `api` depend on `application`. Enforce it with `import-linter` contracts if the team is large.

Moving between layouts: layered → modular is a mechanical move of files into per-domain packages and is worth doing as soon as a second or third domain appears. Modules in a modular monolith are also the natural seams for later extracting microservices; extract only when there is an operational reason (independent scaling, deployment cadence, team ownership), not by default.

## Layering rules

These keep any layout maintainable:

- **Router**: parse/validate input (via signatures), call one service method, convert the result to a response schema. No queries, no business rules, no try/except for domain errors.
- **Service**: business logic and orchestration (transactions spanning repositories, calls to other modules' services, external clients). Knows nothing about HTTP: no `Request`, no `HTTPException`, no status codes.
- **Repository**: data access only. Returns domain/ORM objects. The service depends on a `Protocol`, so tests and future storage changes swap implementations freely.
- **Cross-module access** goes through the other module's service, imported explicitly (`from app.users import service as users_service`), never by reaching into its repository or models. This keeps module boundaries real.

## Dependency injection

Use `Annotated` aliases so signatures stay short and consistent:

```python
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
```

Good uses of dependencies beyond wiring: authentication/authorization (`require_role("admin")`), loading and validating a path resource (`valid_order: Annotated[Order, Depends(get_order_or_404)]`), pagination params, feature flags. Dependencies are cached per request, so `get_session` used by several dependencies yields the same session. Prefer `async def` dependencies when they do I/O; sync dependencies run in a threadpool.

Shared, long-lived resources (DB engine, `httpx.AsyncClient`, Redis pool) are created in `lifespan`, stored on `app.state`, and handed out by a dependency that reads `request.app.state`. Don't create clients per request.

## Settings

`pydantic-settings` with a cached `get_settings()` (template: `config.py`). Guidelines: group related settings with nested models or `env_prefix` (`DB_HOST`, `DB_PORT`); use `SecretStr` for secrets so they don't appear in logs or reprs; validate at startup so misconfiguration fails fast; in tests override with `app.dependency_overrides[get_settings] = lambda: Settings(environment="test")` or by clearing the `lru_cache` after setting env vars. Large apps can give each module its own settings class.

## Database: async SQLAlchemy 2.0 + Alembic

Add with `uv add "sqlalchemy[asyncio]" asyncpg alembic` and `uv run alembic init -t async migrations`.

```python
# db.py
from collections.abc import AsyncIterator
from typing import Annotated
from fastapi import Depends
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

engine = create_async_engine(str(get_settings().database_url), pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```

Points that matter: one session per request (the dependency above), commit at the unit-of-work boundary rather than inside each repository method, an explicit naming convention so Alembic generates stable constraint names, `expire_on_commit=False` so returned objects stay usable after commit, and `engine.dispose()` in lifespan shutdown. Use `Mapped[...]`/`mapped_column` typed models so mypy understands them. Avoid lazy loading in async code (it raises); load relationships explicitly with `selectinload`. Review every autogenerated migration before committing it. SQLModel is an acceptable alternative for simple CRUD services, but it couples ORM and API schemas, which works against the separation recommended here.

Swap the in-memory repository from the scaffold for a SQLAlchemy one implementing the same Protocol; the service and router don't change.

## Errors

Domain exceptions live with their module (`OrderNotFoundError(NotFoundError)`), are raised by services, and are translated in one handler into a consistent envelope (`{"error": {"code": ..., "message": ...}}`, see template `exceptions.py`). Also consider a handler for `RequestValidationError` if clients need the same envelope for 422s, and a catch-all that logs unexpected exceptions with the request ID and returns a generic 500 without leaking internals. `HTTPException` is acceptable in dependencies that are inherently HTTP-level (auth), not in services.

## Schemas

Separate `XCreate`, `XUpdate` (all fields optional, applied with `model_dump(exclude_unset=True)` so PATCH doesn't null out omitted fields), and `XRead` (`from_attributes=True`). Never return ORM objects whose shape you haven't declared; declare the return type or `response_model` so internal fields can't leak. Use `Field` constraints for validation and a shared base model with project-wide config (e.g. `alias_generator=to_camel` and `populate_by_name=True` if the API contract is camelCase). Use `Decimal` for money, timezone-aware `datetime` for timestamps.

## Async correctness

- `async def` endpoints and dependencies must not block: no `requests`, `time.sleep`, sync DB drivers or heavy CPU work inside them. Ruff's `ASYNC` rules catch common cases.
- If a library is sync-only, declare the endpoint with plain `def` (FastAPI runs it in a threadpool) or wrap the call: `await run_in_threadpool(fn, *args)`.
- CPU-heavy work (image processing, ML inference, big pandas jobs) goes to a process pool or a task queue, not the event loop.
- Use `httpx.AsyncClient` (one shared instance with timeouts) for outbound HTTP.

## Testing

- Build the app with `create_app()` per test and use `app.dependency_overrides` to inject fakes or test sessions (template `tests/conftest.py`).
- `httpx.AsyncClient(transport=ASGITransport(app=app))` for async tests. Note it does not run lifespan; use `asgi-lifespan`'s `LifespanManager` when tests need startup resources.
- Unit-test services directly with fake repositories: fast and HTTP-free.
- Integration tests run against a real database (Testcontainers Postgres), each test in a transaction rolled back at the end or with tables truncated, marked `@pytest.mark.integration`.
- Contract safety: snapshot `app.openapi()` in a test so accidental API changes show up in review.

## Security

Authentication via OAuth2/JWT with `fastapi.security` primitives in an `auth` module exposing a `CurrentUser` dependency; verify tokens with a maintained library (`pyjwt`, `authlib`) and hash passwords with `argon2-cffi` or `pwdlib`. Configure CORS explicitly (never `allow_origins=["*"]` with credentials). Disable `/docs` in production or protect it (the template does this based on `environment`). Add rate limiting at the gateway or with `slowapi`. Keep secrets in env/secret managers, typed as `SecretStr`.

## Observability

Structured logging (JSON in production, e.g. `structlog` or `python-json-logger`) with a request ID middleware that also returns `X-Request-ID`; OpenTelemetry instrumentation (`opentelemetry-instrumentation-fastapi`) for traces; Prometheus metrics (`prometheus-fastapi-instrumentator`); `/health` for liveness and `/ready` checking critical dependencies for readiness (both in the template). Sentry or similar for error tracking.

## Scaling

- Stateless processes: no in-memory sessions or caches that must be shared; use Redis. Then scale horizontally behind a load balancer.
- Process model: in Kubernetes, one Uvicorn process per container and scale replicas; on a VM, `uvicorn --workers N` or Gunicorn with Uvicorn workers.
- Connection budgets: replicas × workers × (pool_size + max_overflow) must fit the database's `max_connections`; put PgBouncer in front of Postgres when it doesn't.
- Background work: `BackgroundTasks` only for small, loss-tolerant jobs (sending an email after a response). Anything needing retries, scheduling or durability goes to a queue: Celery, Dramatiq, ARQ, Taskiq, or a broker such as RabbitMQ/Kafka for event-driven flows. Keep worker code calling the same services the API uses.
- Caching: HTTP caching headers for public reads, Redis for computed results, with explicit invalidation in the service layer.
- Pagination on every list endpoint (offset/limit for small sets, cursor/keyset for large or fast-changing ones).
- API versioning via router prefixes (`/api/v1`); add `/api/v2` routers alongside rather than changing v1 contracts.

## Checklist: adding a feature module (modular layout)

1. Copy the `items/` package pattern: `models.py`, `schemas.py`, `repository.py` (Protocol + implementation), `service.py`, `exceptions.py`, `dependencies.py`, `router.py`. For a small module, put the `get_<x>_service` function and its `Annotated` alias at the top of `router.py` and skip `dependencies.py`; split it out when another module needs the dependency or tests override it often.
2. Register the router in `api.py`.
3. If it has tables: model inherits `Base`, then `make migration m="add <feature>"`, review, `make migrate`.
4. Tests in `tests/<feature>/`: service tests with a fake repository, router tests through the client.
5. `make check`.
