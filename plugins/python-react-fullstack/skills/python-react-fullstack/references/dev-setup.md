# Dev Setup, Deployment Shape, CI

## Contents
1. Monorepo and tooling
2. Same-origin in development: Vite proxy
3. Same-origin in production
4. When you really need CORS
5. Environment configuration
6. Docker Compose for local dev
7. CI pipeline

## 1. Monorepo and tooling

One repo, two apps, one generated contract. `backend/` uses `uv` (`pyproject.toml`, `uv.lock`); `frontend/` uses npm/pnpm. A root `Makefile` (or `justfile`) is the entry point:

```makefile
.PHONY: dev api test lint
dev:          ## run db, backend and frontend
	docker compose up -d db
	(cd backend && uv run fastapi dev app/main.py --port 8000) & (cd frontend && npm run dev)
api:          ## export OpenAPI + regenerate TS types
	cd backend && uv run python -m app.scripts.export_openapi ../contract/openapi.json
	cd frontend && npm run api:gen
test:
	cd backend && uv run pytest
	cd frontend && npm test -- --run
lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && npm run lint && npm run typecheck
```

Optional: a pre-commit hook that runs `make api` when files under `backend/app/**/schemas.py` or routers change.

## 2. Same-origin in development: Vite proxy

```ts
// frontend/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
    },
  },
});
```

Keep the `@/` alias in `tsconfig.json` as `"paths": { "@/*": ["./src/*"] }` with no `baseUrl`: TypeScript 6 removed `baseUrl`, and relative `paths` work on 5.x too.

The browser only ever talks to `localhost:5173`, so cookies are first-party, no CORS preflights happen, and `env.apiBaseUrl` is `''`. `ws: true` forwards WebSocket upgrades.

## 3. Same-origin in production

Preferred: one origin, path-routed.

- **Reverse proxy** (nginx, Caddy, Traefik, cloud LB): `/api/*` → FastAPI, everything else → static SPA build with fallback to `index.html`.
- **Or FastAPI serves the SPA**: mount the built `dist/` with `StaticFiles` and a catch-all that returns `index.html` for non-`/api` paths. Fine for small deployments; a CDN in front is better at scale.

Cache rules: hashed assets (`/assets/*`) immutable for a year; `index.html` `no-cache`; API responses `no-store` unless deliberately cacheable.

## 4. When you really need CORS

Only if the SPA and API must live on different sites (e.g. `app.example.com` → `api.othervendor.com`) or third parties call the API from browsers.

- `allow_origins` = explicit list from settings; never `["*"]` together with `allow_credentials=True` (browsers reject it, and regex-wildcards that echo any origin are a vulnerability).
- Different subdomains of the same registrable domain (`app.example.com` / `api.example.com`) are same-site: `SameSite=Lax` cookies still work, but CORS is still required because they're different origins.
- Different sites: cookies need `SameSite=None; Secure` and are increasingly blocked as third-party cookies. Switch to bearer tokens (auth.md option C) instead of fighting this.

## 5. Environment configuration

- Backend: `pydantic-settings` with an `APP_` prefix; `.env` for local only, real secrets from the platform's secret store. Commit `.env.example`.
- Frontend: only `VITE_*` variables reach the bundle and they are public. Parse them once:

```ts
// frontend/src/config/env.ts
import { z } from 'zod';
const schema = z.object({ VITE_API_BASE_URL: z.string().default('') });
const parsed = schema.parse(import.meta.env);
export const env = { apiBaseUrl: parsed.VITE_API_BASE_URL };
```

## 6. Docker Compose for local dev

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:17
    environment: { POSTGRES_USER: app, POSTGRES_PASSWORD: app, POSTGRES_DB: app }
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U app"], interval: 5s, retries: 10 }
  redis:                                   # only if using sessions/jobs/streams in Redis
    image: redis:7
    ports: ["6379:6379"]
  backend:
    build: ./backend
    command: uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
    env_file: ./backend/.env
    environment: { APP_DATABASE_URL: postgresql+asyncpg://app:app@db:5432/app }
    volumes: ["./backend/app:/app/app"]
    ports: ["8000:8000"]
    depends_on: { db: { condition: service_healthy } }
  frontend:
    build: ./frontend
    command: npm run dev -- --host 0.0.0.0
    environment: { VITE_PROXY_TARGET: http://backend:8000 }
    volumes: ["./frontend/src:/app/src"]
    ports: ["5173:5173"]
volumes: { pgdata: {} }
```

When the frontend runs inside Compose, read the proxy target from `process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'` in `vite.config.ts`. Many teams run only `db`/`redis` in Docker and the two apps natively for faster reloads — both are fine.

## 7. CI pipeline

Run on every PR, in this order (fail fast on contract drift):

1. **Backend:** `uv sync --frozen` → `ruff check` → `ruff format --check` → `mypy app` → `pytest` (with a Postgres service container).
2. **Contract:** `make api` → `git diff --exit-code contract/ frontend/src/lib/api/schema.d.ts`.
3. **Optional breaking-change report:** `oasdiff breaking origin/main:contract/openapi.json contract/openapi.json`.
4. **Frontend:** `npm ci` → `lint` → `typecheck` → `vitest --run` → `vite build`.
5. **Optional E2E:** Playwright against the Compose stack for critical flows (login, the main happy path, one streaming interaction).
