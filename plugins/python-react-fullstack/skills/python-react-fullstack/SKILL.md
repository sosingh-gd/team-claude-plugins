---
name: python-react-fullstack
description: Full-stack standards for a Python FastAPI backend with a React + TypeScript frontend, focused on how they communicate. Covers FastAPI layout (routers, services, repositories), Pydantic schemas as the single source of truth, OpenAPI-generated TypeScript types and a typed fetch client, TanStack Query hooks, RFC 9457 errors, pagination, choosing auth per project (cookie sessions, BFF/OIDC, bearer JWT), SSE streaming for LLM agents, uploads, background jobs, WebSockets, CORS/proxy and dev setup. Use this skill whenever the user builds, scaffolds, reviews or debugs anything crossing the Python–React boundary, such as a new endpoint plus the hook that calls it, frontend types drifting from the backend, CORS or cookie errors, streaming agent output to the UI, SPA login, or any full-stack Python + React app, even if they only mention FastAPI, Pydantic, an endpoint, or connecting a frontend to a backend. Use with react-architecture (frontend structure and standards) and python-architecture (backend tooling and Python standards).
---

# Python Full-Stack: FastAPI ↔ React

**Core idea: one contract, flowing one way.** The backend's Pydantic schemas define the API. FastAPI turns them into OpenAPI. The frontend generates TypeScript types from that OpenAPI and calls the API through one typed client. Nobody hand-writes a type the backend already defines, so a breaking backend change becomes a TypeScript compile error instead of a production bug.

When a situation isn't covered below, choose the option that keeps the contract machine-checked end to end and the code easiest to read.

## Readability comes first

When readability and abstraction pull in different directions, choose readability. Someone new to the code should be able to read a file from top to bottom and understand it without jumping through layers.

- **Add an abstraction only for a second real use that exists today.** That covers base classes, Protocols and interfaces, generic helpers, factories, wrappers, and extra layers or files. "We might need it later" is not a reason; adding it later is cheap.
- **A few repeated lines beat a shared helper that hides what the code does.**
- **Call things directly.** Use the library or function you need instead of an indirection built for flexibility nobody asked for.
- **No clever tricks.** Name things for what they do. If a pattern needs a comment to explain how it works, choose a plainer one.
- **This outranks the rest of this skill.** If a rule below would make this project's code harder to read, favor readability and say in one line which rule you relaxed.

The contract rules (generated types, one HTTP client, one error format) are the exception worth keeping: they remove hand-written code rather than add layers.

## The project's own rules come first

Read the project's `CLAUDE.md` (and any README conventions) before applying this skill. If it says to keep things simple, favor readable code over abstractions, skip tests, or use a lighter setup, **follow the project**. This skill's defaults (tests on both sides, strict linting, the full folder structure) are a starting point for teams that haven't decided, not rules that override the project. The contract rules below (generated types, one HTTP client, one error format) are the part worth keeping even in a small project, because they are what catch backend/frontend mismatches.


```
Pydantic schemas ──► FastAPI app.openapi() ──► contract/openapi.json (committed)
                                                        │
                                   openapi-typescript   ▼
React component ◄── TanStack Query hook ◄── openapi-fetch client ◄── src/lib/api/schema.d.ts
```

## Companion skills

This skill owns the **boundary** between backend and frontend. Two companion skills own each side. When they are available (they ship in the same plugin), **load them with the Skill tool** before scaffolding a project or doing substantial work on one side. Don't rebuild their standards from memory.

| Area | Owner |
|---|---|
| Repo layout (`backend/`, `frontend/`, `contract/`), API contract, wire format, errors, auth, streaming, root `Makefile` (`dev`, `api`, `api-check`), Vite proxy, `docker-compose.yml` | **this skill** |
| Backend tooling and Python standards: uv, `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest]` / `[tool.coverage]` in `backend/pyproject.toml`, `backend/Makefile` (`install`, `format`, `lint`, `typecheck`, `test`, `cov`, `check`), pre-commit, Dockerfile, typing, logging, settings | **python-architecture** |
| Everything under `frontend/src` except the API layer: folder structure, components, design-system adapter, coding standards | **react-architecture** |

How they combine:

- **This skill wins on the contract.** If a companion rule would break a contract rule (e.g. camelCase aliases, `ApiModel`, generated types, one HTTP client), follow this skill.
- **Backend package location.** Keep the app at `backend/app/` as shown below, not python-architecture's `src/<package>/` layout, because the templates, `app.…` imports and `export_openapi.py` depend on it. Don't run python-architecture's `scaffold.py` for the backend of a full-stack repo; use its templates (`pyproject.fastapi.toml` tool sections, `Makefile.fastapi`, `Dockerfile`, `pre-commit-config.yaml`, `ci.yml`) and adapt paths from `src/<package>` to `app`.
- **pyproject.** Start from this skill's `project/pyproject.toml` for dependencies and the `pytest-asyncio` settings, then take the tool sections from python-architecture.
- **Makefiles.** The root `Makefile` (this skill) orchestrates both sides; `backend/Makefile` follows python-architecture. Root `lint`/`test` may call `make -C backend check`.
- **If a companion skill isn't available,** use this skill's templates and stack defaults as they are.

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
│       └── features/<f>/<f>.api.ts  # calls, query keys and hooks; split only when it gets long
├── contract/openapi.json     # GENERATED from backend, committed, diffed in CI
├── Makefile                  # `make api` = export spec + regenerate types
└── docker-compose.yml
```

Backend and frontend **features mirror each other by name** (`backend/app/features/orders` ↔ `frontend/src/features/orders`). This makes it obvious where both halves of a change live. Under `frontend/src`, react-architecture owns the structure; this skill only adds the API layer conventions (see Companion skills).

## The ten rules

1. **Pydantic schemas are the contract.** Separate models per direction (`OrderCreate`, `OrderUpdate`, `OrderRead`). Never return ORM models directly; always declare `response_model` (or a return annotation) so OpenAPI is complete.
2. **camelCase on the wire, snake_case in Python.** All schemas inherit one `ApiModel` base with a camelCase alias generator, so TypeScript code reads naturally and Python stays idiomatic.
3. **Stable operation IDs.** Configure `generate_unique_id_function` so generated names don't change when a path or tag changes.
4. **Generated code is committed and never edited.** CI regenerates the spec and types and fails on any diff. Frontend-only shapes (view models, form state) live in the feature's `types.ts` and are derived from generated types.
5. **One HTTP client.** `lib/http.ts` exports the typed client and `ApiError`. Only the feature API files (`features/<f>/<f>.api.ts`) call it; components call query hooks, never `fetch`.
6. **One error format.** Every non-2xx response is RFC 9457 Problem Details (`application/problem+json`) with a machine-readable `code` and optional field `errors`. The frontend turns it into one `ApiError` class, and maps 422 field errors straight onto React Hook Form.
7. **Thin routers.** Routers translate HTTP ↔ domain (parse, call service, return schema). Business logic lives in services, data access in repositories. Services raise domain errors; they never import FastAPI.
8. **Same-origin by default.** Vite's dev proxy in development and a reverse proxy in production put the SPA and `/api` on one origin, which removes most CORS and cookie problems. CORS is the fallback for genuinely cross-origin setups, with explicit origins — never `*` with credentials.
9. **Pick auth by deployment shape, not habit.** Use the decision table in `references/auth.md`. Never put long-lived tokens in `localStorage`.
10. **Stream with SSE, converse with WebSockets.** Server→client streams (LLM tokens, agent steps, progress) use SSE over `fetch` with a typed event union. For chat, create the conversation first and then stream into it, and write the streamed text into the cached conversation (`references/streaming.md`, section 1). Use WebSockets only for genuinely bidirectional, low-latency traffic.

## Workflow: adding a feature end to end

Follow this order; each step makes the next one type-checked.

1. **Schemas** — `backend/app/features/<f>/schemas.py`: request and response models on `ApiModel`.
2. **Service + repository** — business rules and queries; raise `NotFoundError`, `ConflictError`, etc.
3. **Router** — thin endpoint with `response_model`, status code, dependencies; include it in `api/v1/router.py`.
4. **Backend tests** — `httpx.AsyncClient` against the app; assert status codes and the problem-details body for failures.
5. **Regenerate the contract** — `make api` (exports `contract/openapi.json`, runs `openapi-typescript`).
6. **Frontend API layer** — one `features/<f>/<f>.api.ts` with the raw calls, the query keys and the hooks. Re-export domain types in `features/<f>/types.ts`. Split it into an `api/` folder (calls, keys, hooks) only once it grows past about 150 lines.
7. **UI** — components use the hooks; mutations invalidate the right keys; forms map `ApiError.fieldErrors` onto fields.
8. **Frontend tests** — MSW handlers typed from the generated schema. Skip steps 4 and 8 if the project's `CLAUDE.md` says not to write tests.

## Which reference to read

| Situation | Read |
|---|---|
| Scaffolding or reviewing backend structure, DI, settings, DB sessions, testing | `references/backend-structure.md` |
| Wire conventions, errors, pagination, codegen, `lib/http.ts`, query hooks, CI drift check | `references/api-contract.md` |
| Login, sessions, tokens, CSRF, OIDC/SSO, 401 handling | `references/auth.md` |
| Streaming LLM/agent output, chat UIs, SSE, reconnects, WebSockets | `references/streaming.md` (start with section 1; sections 6–7 are optional extras) |
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
| `backend/feature/*.py` | `backend/app/features/{{feature_snake}}/` (one set per feature; the service wiring lives in `router.py`) |
| `backend/agent/*.py` | `backend/app/features/agent/` (only for chat/streaming: conversations + SSE replies; include its router in `api/v1/router.py` and add `AgentEvent` to `EXTRA_MODELS`) |
| `backend/tests/conftest.py`, `backend/tests/test_feature_api.py` | `backend/tests/`, `backend/tests/test_{{feature_snake}}_api.py` |
| `frontend/config/env.ts`, `frontend/lib/{http,queryClient,forms}.ts` | `frontend/src/config/`, `frontend/src/lib/` |
| `frontend/feature/types.ts` | `frontend/src/features/{{entities}}/types.ts` |
| `frontend/feature/api.ts`, `frontend/feature/mocks.ts` | `frontend/src/features/{{entities}}/{{entities}}.api.ts`, `{{entities}}.mocks.ts` (mocks only if the project has tests) |
| `frontend/chat/chat.api.ts`, `frontend/chat/useChat.ts` | `frontend/src/features/chat/` |
| `project/Makefile`, `project/docker-compose.yml`, `project/vite.config.ts` | repo root, repo root, `frontend/` |
| `project/pyproject.toml`, `project/env.example` | `backend/pyproject.toml`, `backend/.env.example` |
| `project/package.scripts.json` | merge into `frontend/package.json` |

Create empty `__init__.py` files in each backend package. The domain columns in `feature/models.py` and `feature/schemas.py` (`name`, `description`) are placeholders; replace them with the real fields and keep the three schemas (`Create`, `Update`, `Read`) in sync with the model.

## Stack defaults (unless the project already chose otherwise)

- **Backend:** tooling and code standards as in `python-architecture` when available. Python 3.12+, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.x (async) + Alembic, `uv` for dependencies, Ruff + mypy (strict), pytest + pytest-asyncio + httpx.
- **Contract:** OpenAPI 3.1 from FastAPI → `openapi-typescript` → `openapi-fetch`. Orval or `@hey-api/openapi-ts` are acceptable if the team prefers generated hooks, but keep the generated hooks inside the feature that uses them.
- **Frontend:** as in `react-architecture` — Vite, TypeScript strict, TanStack Query, React Hook Form + Zod, and Vitest + RTL + MSW when the project has tests.
- **Streaming:** `StreamingResponse` subclass with `text/event-stream` on the backend; `fetch` + `eventsource-parser` on the frontend.

If the existing project diverges (Axios instead of openapi-fetch, snake_case JSON, sync SQLAlchemy), follow the project and briefly note where it differs from this skill. Don't migrate unprompted.

## How to respond

- **New feature or endpoint:** start from `assets/templates/backend/feature/` and `frontend/feature/`; show the file tree for both sides first, then each file under a heading with its full path, in workflow order (schemas → service → router → tests → generated-types note → `<f>.api.ts` → component usage). Remind the user to run `make api` between backend and frontend.
- **Scaffolding a project:** first load `python-architecture` and `react-architecture` if available (see Companion skills). Then start from `assets/templates/` and produce the full repo layout, `backend/app/main.py`, `core/config.py`, `core/errors.py`, `ApiModel`, one example feature end to end on both sides, `export_openapi.py`, `vite.config.ts` proxy, `lib/http.ts`, `Makefile`, `docker-compose.yml`, and the CI steps from `references/dev-setup.md`. Apply python-architecture's tooling to `backend/` and react-architecture's structure to `frontend/src`, then run `make check` in `backend/` and the frontend lint and type-check before handing back.
- **Reviewing or debugging:** list contract violations first (hand-written types duplicating backend schemas, `fetch` in components, ORM objects returned, inconsistent error shapes, tokens in localStorage, wildcard CORS with credentials), then layering issues, then everything else, then the corrected code.
- **Auth questions:** ask at most one question about deployment shape (same origin? external IdP? non-browser clients?) if it isn't clear from context, then recommend one option from the decision table and say why.
- **Chat or streaming UI:** start from section 1 of `references/streaming.md` and the `backend/agent` + `frontend/chat` templates. Add tool-call events or resumable runs only if the user asks for them.
- **Explaining to the user:** describe what changed and why in everyday words, the way you would to a colleague who doesn't know this stack. Explain a technical term in a short phrase the first time (for example "SSE, a way for the server to send text to the browser bit by bit") or leave it out. Name standards such as RFC 9457 only when the user needs to look them up.
- Keep explanations short; let the code and structure carry the message.
