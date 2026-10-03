# Auth Between React and FastAPI

## Contents
1. Decision table
2. Option A: httpOnly cookie session (default for SPA + own backend)
3. Option B: BFF with external IdP (OIDC/SSO)
4. Option C: Bearer JWT (multiple or non-browser clients)
5. Authorization (who can do what)
6. Frontend: session state and 401 handling

## 1. Decision table

Ask about deployment shape, then pick one row. If unclear, ask one question: "Is the SPA served from the same site as the API, and do users log in with your own accounts or a company IdP?"

| Situation | Choose | Why |
|---|---|---|
| SPA and API on the same site, own user accounts | **A. Cookie session** | Simplest secure option; tokens never touch JS; works with SSE/`EventSource` automatically |
| Same as above but login via Entra ID / Okta / Auth0 / Keycloak / Google | **B. BFF** (backend does OIDC, then issues the cookie from A) | Keeps IdP tokens server-side; SPA code stays identical to A |
| API also serves mobile apps, CLIs, partners, or other services; or the SPA must call the API cross-site | **C. Bearer JWT** (often issued by the IdP; SPA uses PKCE) | Headers work for any client; no cookie/CSRF cross-site issues |
| Internal tool behind a corporate gateway (IAP, oauth2-proxy) | Trust the gateway's identity header, verify its signature | Don't build auth twice |

Never: long-lived tokens in `localStorage`/`sessionStorage`; tokens in URLs (except one-time codes); rolling your own password hashing (use `argon2-cffi` or `pwdlib`).

## 2. Option A: httpOnly cookie session

Session token is an opaque random ID mapped to a server-side session (DB or Redis) — easy to revoke. A signed JWT in the cookie is acceptable if revocation isn't needed, but opaque is the default.

```python
# app/core/security.py
import secrets
from typing import Annotated
from fastapi import Cookie, Depends, Request, Response
from app.core.config import get_settings
from app.core.errors import PermissionDeniedError, UnauthenticatedError

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def set_session_cookies(response: Response, session_id: str, max_age: int = 60 * 60 * 24 * 7) -> None:
    s = get_settings()
    response.set_cookie(SESSION_COOKIE, session_id, max_age=max_age, httponly=True,
                        secure=s.session_cookie_secure, samesite="lax", path="/")
    # Readable by JS on purpose: double-submit CSRF token
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), max_age=max_age, httponly=False,
                        secure=s.session_cookie_secure, samesite="lax", path="/")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def verify_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get("X-CSRF-Token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise PermissionDeniedError("CSRF check failed", code="csrf_failed")


async def get_current_user(
    session_store: SessionStoreDep,               # your DB/Redis-backed store
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    if not session or not (user := await session_store.user_for(session)):
        raise UnauthenticatedError("Not signed in")
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]
```

Apply CSRF to every cookie-authenticated router: `APIRouter(prefix="/api/v1", dependencies=[Depends(verify_csrf)])`. SameSite=Lax already blocks most cross-site POSTs; the double-submit token covers the remaining cases (subdomains, older browsers). The `csrf` middleware in `lib/http.ts` sends the header.

```python
# app/features/auth/router.py
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=MeRead)
async def login(body: LoginRequest, response: Response, service: AuthServiceDep):
    user, session_id = await service.login(body.email, body.password)  # raises UnauthenticatedError
    set_session_cookies(response, session_id)
    return MeRead.model_validate(user)

@router.post("/logout", status_code=204)
async def logout(response: Response, service: AuthServiceDep, session: ...) -> None:
    await service.revoke(session)
    clear_session_cookies(response)

@router.get("/me", response_model=MeRead)
async def me(user: CurrentUser):
    return MeRead.model_validate(user)
```

Login itself must be exempt from `verify_csrf` (no cookie yet) — mount the auth router without that dependency, and rate-limit it. Rotate the session ID on login and privilege change.

Dev note: browsers treat `http://localhost` as a secure context, so `Secure` cookies work through the Vite proxy. If testing via a LAN IP over plain HTTP, set `APP_SESSION_COOKIE_SECURE=false` locally only.

## 3. Option B: BFF with external IdP

The backend is a confidential OIDC client (Authorization Code + PKCE). The SPA never sees IdP tokens.

Flow: SPA navigates (full page) to `GET /api/v1/auth/login` → backend redirects to IdP → IdP redirects to `GET /api/v1/auth/callback` → backend exchanges the code, validates the ID token, upserts the user, stores IdP tokens server-side if it must call downstream APIs, then calls `set_session_cookies` and redirects to the SPA. From then on everything is Option A.

Use `authlib` (Starlette integration) rather than hand-rolling the protocol. Validate `state`, `nonce`, issuer, audience; store the PKCE verifier in a short-lived signed cookie or server-side.

## 4. Option C: Bearer JWT

Backend validates access tokens; it usually doesn't issue them (the IdP does).

```python
# app/core/security.py (bearer variant)
import jwt                      # PyJWT
from jwt import PyJWKClient
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)
_jwks = PyJWKClient(get_settings().oidc_jwks_url, cache_keys=True)


async def get_current_user(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if creds is None:
        raise UnauthenticatedError("Missing bearer token")
    s = get_settings()
    try:
        key = _jwks.get_signing_key_from_jwt(creds.credentials).key
        claims = jwt.decode(creds.credentials, key, algorithms=["RS256", "ES256"],
                            audience=s.oidc_audience, issuer=s.oidc_issuer)
    except jwt.PyJWTError as e:
        raise UnauthenticatedError("Invalid token") from e
    return await load_or_provision_user(claims)
```

`PyJWKClient` fetches synchronously; for high traffic, prefetch keys at startup or run the lookup in a thread. Never accept `alg: none`; always pin algorithms, audience and issuer.

Frontend: use the IdP's SDK (`oidc-client-ts`, MSAL, Auth0 SPA SDK) with PKCE; keep the access token in memory; add it via an openapi-fetch middleware:

```ts
api.use({
  async onRequest({ request }) {
    const token = await auth.getAccessToken(); // SDK handles silent refresh
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    return request;
  },
});
```

Drop the CSRF middleware in this mode — bearer headers aren't sent automatically, so CSRF doesn't apply. SSE must use `fetch` streaming (not `EventSource`) so the header can be attached; see streaming.md.

## 5. Authorization

Authentication answers "who"; authorization belongs in services, not the UI.

```python
def require_role(*roles: str):
    async def dep(user: CurrentUser) -> User:
        if not set(roles) & set(user.roles):
            raise PermissionDeniedError()
        return user
    return Depends(dep)

@router.delete("/{order_id}", status_code=204, dependencies=[require_role("admin")])
```

Row-level rules ("only the order's owner may edit") go in the service where the row is loaded. The frontend can hide buttons using `/auth/me` roles or permissions, but that's UX only.

## 6. Frontend: session state and 401 handling

```ts
// features/session/api/session.queries.ts
export function useMeQuery() {
  return useQuery({
    queryKey: ['session', 'me'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/auth/me', { signal })),
    retry: false,
    staleTime: 5 * 60_000,
  });
}
```

```ts
// lib/queryClient.ts — one global place reacts to expired sessions
import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';

const onError = (err: unknown) => {
  if (isApiError(err) && err.status === 401) {
    queryClient.setQueryData(['session', 'me'], null);
    // router guard sees no user and redirects to /login?next=<current path>
  }
};

export const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: { /* see api-contract.md */ },
});
```

Route guards live in `app/router/` and read `useMeQuery()`; features stay unaware of auth plumbing. On logout, call the endpoint, then `queryClient.clear()`.
