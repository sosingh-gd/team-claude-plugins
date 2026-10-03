---
name: python-react-fullstack
description: Full-stack standards for a Python FastAPI backend with a React + TypeScript frontend, focused on how they communicate. Covers FastAPI layout (routers, services, repositories), Pydantic schemas as the single source of truth, OpenAPI-generated TypeScript types and a typed fetch client, TanStack Query hooks, RFC 9457 errors, pagination, choosing auth per project (cookie sessions, BFF/OIDC, bearer JWT), SSE streaming for LLM agents, uploads, background jobs, WebSockets, CORS/proxy and dev setup. Use this skill whenever the user builds, scaffolds, reviews or debugs anything crossing the Python–React boundary, such as a new endpoint plus the hook that calls it, frontend types drifting from the backend, CORS or cookie errors, streaming agent output to the UI, SPA login, or any full-stack Python + React app, even if they only mention FastAPI, Pydantic, an endpoint, or connecting a frontend to a backend. Use with react-architecture, which owns frontend folder structure.
---

# Python Full-Stack: FastAPI ↔ React

**Core idea: one contract, flowing one way.** The backend's Pydantic schemas define the API. FastAPI turns them into OpenAPI. The frontend generates TypeScript types from that OpenAPI and calls the API through one typed client. Nobody hand-writes a type the backend already defines, so a breaking backend change becomes a TypeScript compile error instead of a production bug.

When a situation isn't covered below, choose the option that keeps the contract machine-checked end to end.

```
Pydantic schemas ──► FastAPI app.openapi() ──► contract/openapi.json (committed)
                                                        │
                                   openapi-typescript   ▼
React component ◄── TanStack Query hook ◄── openapi-fetch client ◄── src/lib/api/schema.d.ts
```

## Repository layout

```
<project>/
├── backend/                  # FastAPI app — layout in references/backend-structure.md
│   ├── app/
│   │   ├── main.py           # create_app(): middleware, routers, exception handlers
│   │   ├── core/             # config, errors, security, logging
│   │   ├── db/               # engine/session, Base
│   │   ├── api/              # deps.py, v1/router.py (mounts feature routers)
│   │   ├── features/<f>/     # router.py, schemas.py, service.py, repository.py, models.py
│   │   └── scripts/export_openapi.py
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── frontend/                 # React + Vite — layout owned by the react-architecture skill
│   └── src/
│       ├── lib/api/schema.d.ts   # GENERATED — never edit
│       ├── lib/http.ts           # the one typed client + ApiError
│       └── features/<f>/api/     # <f>.api.ts, <f>.queries.ts, <f>.keys.ts
├── contract/openapi.json     # GENERATED from backend, committed, diffed in CI
├── Makefile                  # `make api` = export spec + regenerate types
└── docker-compose.yml
```

Backend and frontend **features mirror each other by name** (`backend/app/features/orders` ↔ `frontend/src/features/orders`). This makes it obvious where both halves of a change live. If the `react-architecture` skill is available, follow it for everything under `frontend/src`; this skill only adds the API layer conventions.

## The ten rules

1. **Pydantic schemas are the contract.** Separate models per direction (`OrderCreate`, `OrderUpdate`, `OrderRead`). Never return ORM models directly; always declare `response_model` (or a return annotation) so OpenAPI is complete.
2. **camelCase on the wire, snake_case in Python.** All schemas inherit one `ApiModel` base with a camelCase alias generator, so TypeScript code reads naturally and Python stays idiomatic.
3. **Stable operation IDs.** Configure `generate_unique_id_function` so generated names don't change when a path or tag changes.
4. **Generated code is committed and never edited.** CI regenerates the spec and types and fails on any diff. Frontend-only shapes (view models, form state) live in the feature's `types.ts` and are derived from generated types.
5. **One HTTP client.** `lib/http.ts` exports the typed client and `ApiError`. Only `features/<f>/api/*.api.ts` calls it; components call query hooks, never `fetch`.
6. **One error format.** Every non-2xx response is RFC 9457 Problem Details (`application/problem+json`) with a machine-readable `code` and optional field `errors`. The frontend turns it into one `ApiError` class, and maps 422 field errors straight onto React Hook Form.
7. **Thin routers.** Routers translate HTTP ↔ domain (parse, call service, return schema). Business logic lives in services, data access in repositories. Services raise domain errors; they never import FastAPI.
8. **Same-origin by default.** Vite's dev proxy in development and a reverse proxy in production put the SPA and `/api` on one origin, which removes most CORS and cookie problems. CORS is the fallback for genuinely cross-origin setups, with explicit origins — never `*` with credentials.
9. **Pick auth by deployment shape, not habit.** Use the decision table in `references/auth.md`. Never put long-lived tokens in `localStorage`.
10. **Stream with SSE, converse with WebSockets.** Server→client streams (LLM tokens, agent steps, progress) use SSE over `fetch` with a typed, discriminated event union. Use WebSockets only for genuinely bidirectional, low-latency traffic.

## Workflow: adding a feature end to end

Follow this order; each step makes the next one type-checked.

1. **Schemas** — `backend/app/features/<f>/schemas.py`: request and response models on `ApiModel`.
2. **Service + repository** — business rules and queries; raise `NotFoundError`, `ConflictError`, etc.
3. **Router** — thin endpoint with `response_model`, status code, dependencies; include it in `api/v1/router.py`.
4. **Backend tests** — `httpx.AsyncClient` against the app; assert status codes and the problem-details body for failures.
5. **Regenerate the contract** — `make api` (exports `contract/openapi.json`, runs `openapi-typescript`).
6. **Frontend API layer** — `features/<f>/api/<f>.api.ts` (raw calls), `<f>.keys.ts` (query key factory), `<f>.queries.ts` (hooks). Re-export domain types in `features/<f>/types.ts`.
7. **UI** — components use the hooks; mutations invalidate the right keys; forms map `ApiError.fieldErrors` onto fields.
8. **Frontend tests** — MSW handlers typed from the generated schema.

## Which reference to read

| Situation | Read |
|---|---|
| Scaffolding or reviewing backend structure, DI, settings, DB sessions, testing | `references/backend-structure.md` |
| Wire conventions, errors, pagination, codegen, `lib/http.ts`, query hooks, CI drift check | `references/api-contract.md` |
| Login, sessions, tokens, CSRF, OIDC/SSO, 401 handling | `references/auth.md` |
| Streaming LLM/agent output, SSE, reconnects, WebSockets | `references/streaming.md` |
| Uploads, downloads, long-running jobs, idempotency, optimistic updates, concurrency | `references/other-patterns.md` |
| Monorepo, Vite proxy, CORS, env config, Docker Compose, CI pipeline | `references/dev-setup.md` |

Read only what the task needs. A new CRUD endpoint needs `api-contract.md` and maybe `backend-structure.md`; a chat UI for an agent needs `streaming.md` too.

## Templates

Starting files live in `assets/templates/`, using `{{placeholder}}` substitution like the `react-architecture` templates. Copy them, replace placeholders, and adjust the domain fields. They are verified to work together: backend tests pass, the spec exports, and the frontend type-checks against the generated types.

| Placeholder | Meaning | Example |
|---|---|---|
| `{{Entity}}` | PascalCase singular | `LineItem` |
| `{{entity}}` | camelCase singular (TS) | `lineItem` |
| `{{entities}}` | camelCase plural (TS folder/file names) | `lineItems` |
| `{{entity_snake}}` | snake_case singular (Python, path params) | `line_item` |
| `{{feature_snake}}` | snake_case plural (Python package, table, tag) | `line_items` |
| `{{route}}` | kebab-case plural URL segment | `line-items` |
| `{{AppName}}` / `{{app_name}}` | app display name / package name | `Acme` / `acme` |

| Template (`assets/templates/…`) | Destination |
|---|---|
| `backend/core/{config,schemas,errors,sse}.py` | `backend/app/core/` |
| `backend/db/{base,session}.py` | `backend/app/db/` |
| `backend/api/deps.py`, `backend/api/v1_router.py` | `backend/app/api/deps.py`, `backend/app/api/v1/router.py` |
| `backend/main.py`, `backend/export_openapi.py` | `backend/app/main.py`, `backend/app/scripts/export_openapi.py` |
| `backend/feature/*.py` | `backend/app/features/{{feature_snake}}/` (one set per feature) |
| `backend/agent/*.py` | `backend/app/features/agent/` (only for SSE/agent streaming; add `AgentEvent` to `EXTRA_MODELS`) |
| `backend/tests/conftest.py`, `backend/tests/test_feature_api.py` | `backend/tests/`, `backend/tests/test_{{feature_snake}}_api.py` |
| `frontend/config/env.ts`, `frontend/lib/{http,queryClient,forms}.ts` | `frontend/src/config/`, `frontend/src/lib/` |
| `frontend/feature/types.ts` | `frontend/src/features/{{entities}}/types.ts` |
| `frontend/feature/{api,keys,queries,mocks}.ts` | `frontend/src/features/{{entities}}/api/{{entities}}.{api,keys,queries,mocks}.ts` |
| `frontend/agent/agent.stream.ts`, `frontend/agent/useAgentRun.ts` | `frontend/src/features/agent/api/`, `frontend/src/features/agent/hooks/` |
| `project/Makefile`, `project/docker-compose.yml`, `project/vite.config.ts` | repo root, repo root, `frontend/` |
| `project/pyproject.toml`, `project/env.example` | `backend/pyproject.toml`, `backend/.env.example` |
| `project/package.scripts.json` | merge into `frontend/package.json` |

Create empty `__init__.py` files in each backend package. The domain columns in `feature/models.py` and `feature/schemas.py` (`name`, `description`) are placeholders; replace them with the real fields and keep the three schemas (`Create`, `Update`, `Read`) in sync with the model.

## Stack defaults (unless the project already chose otherwise)

- **Backend:** Python 3.12+, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.x (async) + Alembic, `uv` for dependencies, Ruff + mypy (strict), pytest + pytest-asyncio + httpx.
- **Contract:** OpenAPI 3.1 from FastAPI → `openapi-typescript` → `openapi-fetch`. Orval or `@hey-api/openapi-ts` are acceptable if the team prefers generated hooks, but keep hooks inside `features/<f>/api/`.
- **Frontend:** as in `react-architecture` — Vite, TypeScript strict, TanStack Query, React Hook Form + Zod, Vitest + RTL + MSW.
- **Streaming:** `StreamingResponse` subclass with `text/event-stream` on the backend; `fetch` + `eventsource-parser` on the frontend.

If the existing project diverges (Axios instead of openapi-fetch, snake_case JSON, sync SQLAlchemy), follow the project and briefly note where it differs from this skill. Don't migrate unprompted.

## How to respond

- **New feature or endpoint:** start from `assets/templates/backend/feature/` and `frontend/feature/`; show the file tree for both sides first, then each file under a heading with its full path, in workflow order (schemas → service → router → tests → generated-types note → api/keys/queries → component usage). Remind the user to run `make api` between backend and frontend.
- **Scaffolding a project:** start from `assets/templates/` and produce the full repo layout, `backend/app/main.py`, `core/config.py`, `core/errors.py`, `ApiModel`, one example feature end to end on both sides, `export_openapi.py`, `vite.config.ts` proxy, `lib/http.ts`, `Makefile`, `docker-compose.yml`, and the CI steps from `references/dev-setup.md`.
- **Reviewing or debugging:** list contract violations first (hand-written types duplicating backend schemas, `fetch` in components, ORM objects returned, inconsistent error shapes, tokens in localStorage, wildcard CORS with credentials), then layering issues, then everything else, then the corrected code.
- **Auth questions:** ask at most one question about deployment shape (same origin? external IdP? non-browser clients?) if it isn't clear from context, then recommend one option from the decision table and say why.
- Keep explanations short; let the code and structure carry the message.
