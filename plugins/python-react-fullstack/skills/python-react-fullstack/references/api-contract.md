# API Contract: Conventions, Errors, Codegen, Client

## Contents
1. Wire conventions
2. Error format (RFC 9457 Problem Details)
3. Pagination, filtering, sorting
4. Exporting the OpenAPI spec
5. Generating TypeScript types
6. The frontend client (`lib/http.ts`) and `ApiError`
7. Feature API layer: api / keys / queries
8. Forms: mapping 422 errors onto fields
9. Typed MSW mocks
10. Drift check in CI
11. Versioning and breaking changes

## 1. Wire conventions

| Concern | Convention | Why |
|---|---|---|
| Field casing | camelCase JSON via `ApiModel` aliases | Natural in TS, no mapping layer |
| URLs | `/api/v1/<plural-noun>`, kebab-case segments, no verbs except for actions (`POST /orders/{id}/cancel`) | Predictable, proxy-friendly |
| IDs | UUID strings | Safe to expose, no enumeration |
| Dates/times | ISO 8601 with offset, UTC (`AwareDatetime`) | Unambiguous; format for display on the client |
| Dates without time | `date` → `"2026-10-03"` | Don't fake midnight timestamps |
| Money / precise numbers | `Decimal` → JSON string, or integer minor units | JS numbers lose precision |
| Enums | `StrEnum` → TS string-literal union | Exhaustive `switch` in TS |
| Nullability | `x: str | None` (required, may be null) vs `x: str | None = None` (optional) — be deliberate | Shapes TS `x: string | null` vs `x?: string | null` |
| PATCH | Partial model + `model_dump(exclude_unset=True)` | Distinguishes "not sent" from "set to null" |
| Create | `201` + created resource | Client can update cache without refetch |
| Delete | `204`, no body | |
| Actions with no result | `204`; long ones `202` (see other-patterns.md) | |

Pydantic serializes `Decimal` as a string in JSON mode; the generated TS type is `string`. Parse with a decimal library only where you compute; display as-is.

## 2. Error format (RFC 9457 Problem Details)

Every error response — domain, validation, auth, unhandled — has this shape:

```json
{
  "type": "about:blank",
  "title": "Unprocessable Content",
  "status": 422,
  "code": "validation_error",
  "detail": "Request validation failed",
  "instance": "/api/v1/orders",
  "errors": [{ "field": "lines.0.quantity", "message": "Input should be greater than or equal to 1", "code": "greater_than_equal" }]
}
```

```python
# app/core/errors.py  (AppError hierarchy shown in backend-structure.md)
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.schemas import ApiModel

logger = logging.getLogger(__name__)
PROBLEM_JSON = "application/problem+json"


class FieldError(ApiModel):
    field: str      # dotted camelCase path matching the request JSON
    message: str
    code: str


class ProblemDetail(ApiModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str | None = None
    instance: str | None = None
    errors: list[FieldError] | None = None


COMMON_ERROR_RESPONSES = {
    s: {"model": ProblemDetail, "content": {PROBLEM_JSON: {}}}
    for s in (400, 401, 403, 404, 409, 422, 500)
}


def _problem(request: Request, problem: ProblemDetail, headers: dict | None = None) -> JSONResponse:
    problem.instance = problem.instance or request.url.path
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json", by_alias=True, exclude_none=True),
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return _problem(request, ProblemDetail(title=exc.title, status=exc.status, code=exc.code, detail=exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [
            FieldError(
                # loc is e.g. ("body", "lines", 0, "quantity"); keys are the aliases the client sent
                field=".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]),
                message=e["msg"],
                code=e["type"],
            )
            for e in exc.errors()
        ]
        return _problem(request, ProblemDetail(
            title="Unprocessable Content", status=422, code="validation_error",
            detail="Request validation failed", errors=errors,
        ))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return _problem(request, ProblemDetail(
            title=str(exc.detail) if exc.status_code < 500 else "Internal Server Error",
            status=exc.status_code, code=f"http_{exc.status_code}",
        ), headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _problem(request, ProblemDetail(title="Internal Server Error", status=500, code="internal_error"))
```

Rules: never leak stack traces or SQL in `detail`; `code` values are part of the contract (the UI may branch on them), so treat renaming one as a breaking change.

## 3. Pagination, filtering, sorting

- **Cursor pagination** (`CursorPage[T]`: `items`, `nextCursor`) for feeds, infinite scroll, large or frequently-changing tables. Pairs with `useInfiniteQuery`.
- **Offset pagination** (`OffsetPage[T]`: `items`, `total`, `page`, `pageSize`) for admin tables that need page numbers and totals.
- Filters as query params with explicit types; sorting as `sort=createdAt` / `sort=-createdAt` validated against an allow-list `Literal[...]`.
- Cap `limit`/`pageSize` server-side (e.g. `le=100`).

## 4. Exporting the OpenAPI spec

```python
# app/scripts/export_openapi.py
"""Usage: uv run python -m app.scripts.export_openapi ../contract/openapi.json"""
import json
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.main import create_app

# Models that never appear in a JSON request/response but the frontend still needs typed,
# e.g. SSE event unions (see streaming.md). Import and list them here.
EXTRA_MODELS: list[type[BaseModel]] = []


def build_spec() -> dict:
    spec = create_app().openapi()
    if EXTRA_MODELS:
        _, schema = models_json_schema(
            [(m, "serialization") for m in EXTRA_MODELS],
            ref_template="#/components/schemas/{model}",
            by_alias=True,
        )
        spec.setdefault("components", {}).setdefault("schemas", {}).update(schema.get("$defs", {}))
    return spec


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "../contract/openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_spec(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")
```

`sort_keys=True` keeps diffs stable. Exporting from code (not from a running server) means CI needs no database.

## 5. Generating TypeScript types

```json
// frontend/package.json (scripts)
{
  "api:gen": "openapi-typescript ../contract/openapi.json -o src/lib/api/schema.d.ts",
  "typecheck": "tsc --noEmit"
}
```

```makefile
# Makefile (root)
api:
	cd backend && uv run python -m app.scripts.export_openapi ../contract/openapi.json
	cd frontend && npm run api:gen
```

Add `src/lib/api/schema.d.ts` to `.prettierignore` and ESLint ignores; it's generated.

## 6. The frontend client and `ApiError`

The complete, tested file is `assets/templates/frontend/lib/http.ts.template` (it also exports an `authHeaders()` helper reused by SSE streams). Core of it:

```ts
// frontend/src/lib/http.ts
import createClient, { type Middleware } from 'openapi-fetch';
import type { components, paths } from '@/lib/api/schema';
import { env } from '@/config/env';

export type ProblemDetail = components['schemas']['ProblemDetail'];
export type FieldError = components['schemas']['FieldError'];

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: FieldError[];
  readonly problem?: ProblemDetail;

  constructor(status: number, problem?: ProblemDetail) {
    super(problem?.detail ?? problem?.title ?? `Request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = problem?.code ?? `http_${status}`;
    this.fieldErrors = problem?.errors ?? [];
    this.problem = problem;
  }

  static async fromResponse(res: Response): Promise<ApiError> {
    let problem: ProblemDetail | undefined;
    try {
      problem = (await res.clone().json()) as ProblemDetail;
    } catch {
      /* non-JSON body (proxy error page, etc.) */
    }
    return new ApiError(res.status, problem);
  }
}

export const isApiError = (e: unknown): e is ApiError => e instanceof ApiError;

const csrf: Middleware = {
  onRequest({ request }) {
    // Only needed with cookie auth; see auth.md
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
      const token = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)?.[1];
      if (token) request.headers.set('X-CSRF-Token', decodeURIComponent(token));
    }
    return request;
  },
};

export const api = createClient<paths>({
  baseUrl: env.apiBaseUrl, // '' for same-origin; paths already start with /api/v1
  credentials: 'include',
});
api.use(csrf);

/** Turns openapi-fetch's { data, error } into "return data or throw ApiError". */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok || error !== undefined) {
    throw new ApiError(response.status, error as ProblemDetail | undefined);
  }
  return data as T;
}
```

```ts
// frontend/src/lib/queryClient.ts
import { QueryClient } from '@tanstack/react-query';
import { isApiError } from './http';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(isApiError(err) && err.status < 500) && count < 2, // never retry 4xx
    },
  },
});
```

## 7. Feature API layer

Matches the `react-architecture` feature layout.

```ts
// features/orders/types.ts — re-export generated types under domain names
import type { components, paths } from '@/lib/api/schema';
export type Order = components['schemas']['OrderRead'];
export type OrderCreate = components['schemas']['OrderCreate'];
export type OrderUpdate = components['schemas']['OrderUpdate'];
export type OrderStatus = components['schemas']['OrderStatus'];
export type OrderListParams = NonNullable<paths['/api/v1/orders']['get']['parameters']['query']>;
```

```ts
// features/orders/api/orders.api.ts — raw calls only
import { api, unwrap } from '@/lib/http';
import type { OrderCreate, OrderListParams, OrderUpdate } from '../types';

export const ordersApi = {
  list: (query: OrderListParams, signal?: AbortSignal) =>
    unwrap(api.GET('/api/v1/orders', { params: { query }, signal })),
  get: (orderId: string, signal?: AbortSignal) =>
    unwrap(api.GET('/api/v1/orders/{order_id}', { params: { path: { order_id: orderId } }, signal })),
  create: (body: OrderCreate) => unwrap(api.POST('/api/v1/orders', { body })),
  update: (orderId: string, body: OrderUpdate) =>
    unwrap(api.PATCH('/api/v1/orders/{order_id}', { params: { path: { order_id: orderId } }, body })),
  remove: (orderId: string) =>
    unwrap(api.DELETE('/api/v1/orders/{order_id}', { params: { path: { order_id: orderId } } })),
};
```

Path parameter names come from the Python function signature (`order_id`), not the alias generator. If you prefer camelCase there too, name them `orderId` in the route path and signature — just be consistent.

```ts
// features/orders/api/orders.keys.ts
import type { OrderListParams } from '../types';

export const orderKeys = {
  all: ['orders'] as const,
  lists: () => [...orderKeys.all, 'list'] as const,
  list: (params: OrderListParams) => [...orderKeys.lists(), params] as const,
  detail: (id: string) => [...orderKeys.all, 'detail', id] as const,
};
```

```ts
// features/orders/api/orders.queries.ts
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ordersApi } from './orders.api';
import { orderKeys } from './orders.keys';
import type { OrderListParams, OrderUpdate } from '../types';

export function useOrdersInfiniteQuery(params: Omit<OrderListParams, 'cursor'>) {
  return useInfiniteQuery({
    queryKey: orderKeys.list(params),
    queryFn: ({ pageParam, signal }) => ordersApi.list({ ...params, cursor: pageParam }, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}

export function useOrderQuery(orderId: string) {
  return useQuery({
    queryKey: orderKeys.detail(orderId),
    queryFn: ({ signal }) => ordersApi.get(orderId, signal),
  });
}

export function useCreateOrderMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ordersApi.create,
    onSuccess: (order) => {
      qc.setQueryData(orderKeys.detail(order.id), order);
      return qc.invalidateQueries({ queryKey: orderKeys.lists() });
    },
  });
}

export function useUpdateOrderMutation(orderId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: OrderUpdate) => ordersApi.update(orderId, body),
    onSuccess: (order) => {
      qc.setQueryData(orderKeys.detail(orderId), order);
      return qc.invalidateQueries({ queryKey: orderKeys.lists() });
    },
  });
}
```

## 8. Forms: mapping 422 errors onto fields

Client-side Zod validation gives instant feedback; the server stays authoritative. Map server field errors back:

```ts
// lib/forms.ts
import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';
import { isApiError } from '@/lib/http';

export function applyServerErrors<T extends FieldValues>(err: unknown, setError: UseFormSetError<T>): boolean {
  if (!isApiError(err) || err.fieldErrors.length === 0) return false;
  for (const fe of err.fieldErrors) setError(fe.field as Path<T>, { type: 'server', message: fe.message });
  return true;
}

// in a component
const mutation = useCreateOrderMutation();
const onSubmit = form.handleSubmit((values) =>
  mutation.mutateAsync(values).catch((err) => {
    if (!applyServerErrors(err, form.setError)) toast.error(err.message);
  }),
);
```

Dotted paths like `lines.0.quantity` match React Hook Form's field-array paths, which is why the backend joins `loc` with dots.

Keep Zod schemas aligned with Pydantic constraints manually for UX only; if drift becomes painful, generate Zod from OpenAPI (e.g. `orval` with zod output) rather than hand-maintaining.

## 9. Typed MSW mocks

```ts
// features/orders/api/orders.mocks.ts
import { http, HttpResponse } from 'msw';
import type { Order } from '../types';

export const orderFixture: Order = {
  id: '6f1c…', customerId: '9a2b…', status: 'draft', total: '42.00', note: null,
  createdAt: '2026-10-03T10:00:00Z', updatedAt: '2026-10-03T10:00:00Z',
};

export const ordersHandlers = [
  http.get('/api/v1/orders/:orderId', () => HttpResponse.json(orderFixture)),
];
```

Typing fixtures with generated types means a backend schema change breaks the mocks at compile time instead of silently passing tests. `openapi-msw` can type the handlers themselves if wanted.

## 10. Drift check in CI

```bash
make api
git diff --exit-code contract/openapi.json frontend/src/lib/api/schema.d.ts \
  || { echo "API contract out of date: run 'make api' and commit"; exit 1; }
cd frontend && npm run typecheck
```

Optionally run `oasdiff breaking` between the main branch's spec and the PR's spec to flag breaking changes for review.

## 11. Versioning and breaking changes

- Additive changes (new endpoint, new optional field, new enum value the UI tolerates) ship in place.
- Breaking changes (removed/renamed field, type change, new required request field, renamed error `code`) in a single-deploy monorepo can ship as one PR touching both sides — the drift check plus `tsc` proves the frontend was updated.
- If old clients can still be running (mobile apps, cached SPAs during rollout, third-party consumers), use expand → migrate → contract: add the new field, move clients, then remove the old one. Introduce `/api/v2` only for wholesale redesigns.
