# Streaming: SSE for Agents and LLMs, WebSockets When Needed

## Contents
1. Choosing a transport
2. Typed event contract
3. Backend: SSE endpoint
4. Heartbeats, disconnects, and resources
5. Frontend: fetch-based SSE client
6. Frontend: `useAgentRun` hook
7. Reconnect and resume
8. Infrastructure gotchas
9. WebSockets

## 1. Choosing a transport

| Need | Use |
|---|---|
| Server → client stream started by a request (LLM tokens, agent steps, tool calls, progress) | **SSE over `fetch` POST** |
| Server → client notifications on a long-lived channel (job finished, new message) with cookie auth | SSE via `EventSource` GET (auto-reconnect built in) |
| Status of a job that takes minutes | Polling with TanStack Query `refetchInterval` (other-patterns.md) — simplest, cache-friendly |
| Bidirectional, low latency, client sends many messages mid-stream (collaborative editing, voice, games, interrupting an agent token-by-token) | **WebSocket** |

Why `fetch` over `EventSource` for agents: `EventSource` only does GET with no body and no custom headers. Agent runs need a POST body (messages, tools, settings) and, with bearer auth, an `Authorization` header.

## 2. Typed event contract

Define the stream as a discriminated union of `ApiModel`s. The `type` field is the discriminator on both sides.

```python
# app/features/agent/events.py
from typing import Annotated, Any, Literal, Union
from pydantic import Field, RootModel
from app.core.schemas import ApiModel


class RunStartedEvent(ApiModel):
    type: Literal["run_started"] = "run_started"
    run_id: str


class TextDeltaEvent(ApiModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCallEvent(ApiModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, Any]


class ToolResultEvent(ApiModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    output: Any
    is_error: bool = False


class Usage(ApiModel):
    input_tokens: int
    output_tokens: int


class RunCompletedEvent(ApiModel):
    type: Literal["run_completed"] = "run_completed"
    message_id: str
    usage: Usage | None = None


class RunFailedEvent(ApiModel):
    type: Literal["run_failed"] = "run_failed"
    code: str
    message: str


AgentEventUnion = Annotated[
    Union[RunStartedEvent, TextDeltaEvent, ToolCallEvent, ToolResultEvent, RunCompletedEvent, RunFailedEvent],
    Field(discriminator="type"),
]


class AgentEvent(RootModel[AgentEventUnion]):
    """Every SSE `data:` payload on agent streams is one of these."""
```

Register it for codegen: in `app/scripts/export_openapi.py`, `EXTRA_MODELS = [AgentEvent]`. After `make api`, the frontend has `components['schemas']['AgentEvent']` as a TS union, so `switch (event.type)` is exhaustive. This relies on `json_schema_serialization_defaults_required=True` in `ApiModel` (backend-structure.md): without it the defaulted `type` field is generated as optional and narrowing breaks.

Every stream ends with exactly one terminal event (`run_completed` or `run_failed`). The client treats a stream that closes without one as a dropped connection.

## 3. Backend: SSE endpoint

```python
# app/core/sse.py
from starlette.responses import StreamingResponse
from app.core.schemas import ApiModel


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"

    # Keep `status_code` explicit: FastAPI inspects this signature when building OpenAPI.
    def __init__(self, content, status_code: int = 200, headers: dict[str, str] | None = None, **kwargs):
        merged = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **(headers or {})}
        super().__init__(content, status_code=status_code, headers=merged, **kwargs)


def format_sse(event: ApiModel, *, event_id: str | None = None) -> str:
    data = event.model_dump_json(by_alias=True)       # single line, so one `data:` field suffices
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {getattr(event, 'type', 'message')}\ndata: {data}\n\n"


SSE_PING = ": ping\n\n"   # comment line; ignored by parsers, keeps proxies from timing out
```

This hand-rolled response works on any FastAPI version. Recent FastAPI releases also ship a native `fastapi.sse` module (`EventSourceResponse`, `ServerSentEvent`, built-in keepalive). If the project's FastAPI has it, using it is fine; keep the typed `AgentEvent` union, the terminal-event rule, and the export to OpenAPI either way.

```python
# app/features/agent/router.py
import asyncio
import logging
from fastapi import APIRouter, Request
from app.api.deps import CurrentUser
from app.core.sse import EventStreamResponse, format_sse
from .deps import AgentServiceDep
from .events import RunFailedEvent
from .schemas import AgentRunRequest
from .streaming import with_heartbeat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/runs/stream",
    response_class=EventStreamResponse,
    responses={200: {"description": "SSE stream of AgentEvent",
                     "content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/AgentEvent"}}}}},
)
async def stream_agent_run(body: AgentRunRequest, request: Request, user: CurrentUser, agent: AgentServiceDep):
    async def events():
        seq = 0
        try:
            async for item in with_heartbeat(agent.run(body, user), interval=15):
                if await request.is_disconnected():
                    break
                if isinstance(item, str):          # heartbeat
                    yield item
                    continue
                seq += 1
                yield format_sse(item, event_id=str(seq))
        except asyncio.CancelledError:
            raise                                  # client went away; let cleanup run
        except Exception:
            logger.exception("agent run failed")
            yield format_sse(RunFailedEvent(code="agent_failed", message="The agent run failed"))

    return EventStreamResponse(events())
```

`agent.run(...)` is an async generator in the service yielding event models. It wraps whatever LLM SDK or agent framework the project uses and translates its native events into `AgentEvent` types, so the frontend contract doesn't change if the provider does.

```python
# app/features/agent/service.py (shape only)
class AgentService:
    async def run(self, req: AgentRunRequest, user: User) -> AsyncIterator[ApiModel]:
        run_id = await self.runs.create(user.id, req)
        yield RunStartedEvent(run_id=run_id)
        async for chunk in self.llm.stream(...):      # provider SDK
            yield TextDeltaEvent(text=chunk.text)     # map provider events → contract events
        message_id = await self.save_final_message(run_id, ...)
        yield RunCompletedEvent(message_id=message_id, usage=...)
```

Validation and auth errors happen before streaming starts, so they still return normal Problem Details with a 4xx status. Once the 200 and headers are sent, errors can only be reported as a `run_failed` event.

## 4. Heartbeats, disconnects, and resources

```python
# app/features/agent/streaming.py
import asyncio
from collections.abc import AsyncIterator
from typing import TypeVar
from app.core.sse import SSE_PING

T = TypeVar("T")


async def with_heartbeat(source: AsyncIterator[T], interval: float = 15.0) -> AsyncIterator[T | str]:
    """Yield items from source, inserting SSE ping comments during silences (e.g. long tool calls)."""
    it = aiter(source)
    pending = asyncio.ensure_future(anext(it))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield SSE_PING
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            yield item
            pending = asyncio.ensure_future(anext(it))
    finally:
        pending.cancel()
        if hasattr(it, "aclose"):
            await it.aclose()
```

- **Cancel upstream work on disconnect.** When the client aborts, Starlette cancels the generator; `aclose()` propagates that into the service so the LLM call stops and you stop paying for tokens.
- **Don't hold a request-scoped DB session for the whole stream.** Streams can last minutes. Inside the service, open short sessions via `session_factory()` for each write (create run, save final message).
- **Persist as you go** if partial output matters: save the final assistant message (or checkpoints) server-side, so a page refresh can load it via a normal GET.

## 5. Frontend: fetch-based SSE client

```ts
// features/agent/api/agent.stream.ts
import { createParser, type EventSourceMessage } from 'eventsource-parser';
import { ApiError } from '@/lib/http';
import { env } from '@/config/env';
import type { AgentEvent, AgentRunRequest } from '../types';  // re-exported from generated schema

export async function streamAgentRun(
  body: AgentRunRequest,
  opts: { signal: AbortSignal; onEvent: (e: AgentEvent) => void; headers?: HeadersInit },
): Promise<void> {
  const res = await fetch(`${env.apiBaseUrl}/api/v1/agent/runs/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...opts.headers },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!res.ok || !res.body) throw await ApiError.fromResponse(res);  // 4xx before stream = Problem Details

  let terminal = false;
  const parser = createParser({
    onEvent(msg: EventSourceMessage) {
      const event = JSON.parse(msg.data) as AgentEvent;
      if (event.type === 'run_completed' || event.type === 'run_failed') terminal = true;
      opts.onEvent(event);
    },
  });

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.feed(value);
  }
  if (!terminal && !opts.signal.aborted) throw new ApiError(0, undefined);  // dropped mid-stream
}
```

Pass the CSRF header (cookie auth) or `Authorization` (bearer) through `opts.headers` (the template `assets/templates/frontend/agent/agent.stream.ts.template` does this with `authHeaders()` from `lib/http.ts`) — this call bypasses openapi-fetch, so its middleware doesn't run. A small shared `authHeaders()` helper in `lib/http.ts` keeps both paths consistent.

## 6. Frontend: `useAgentRun` hook

Streams don't fit TanStack Query's request/response cache, so accumulate with a reducer and hand off to the query cache when done.

```ts
// features/agent/hooks/useAgentRun.ts
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { streamAgentRun } from '../api/agent.stream';
import { conversationKeys } from '../api/agent.keys';
import type { AgentEvent, AgentRunRequest } from '../types';

type ToolCall = { callId: string; name: string; arguments: unknown; output?: unknown; isError?: boolean };
type State = {
  status: 'idle' | 'streaming' | 'done' | 'error';
  text: string;
  toolCalls: ToolCall[];
  runId?: string;
  error?: string;
};
type Action = { type: 'start' } | { type: 'event'; event: AgentEvent } | { type: 'fail'; message: string };

const initial: State = { status: 'idle', text: '', toolCalls: [] };

function reducer(state: State, action: Action): State {
  if (action.type === 'start') return { ...initial, status: 'streaming' };
  if (action.type === 'fail') return { ...state, status: 'error', error: action.message };
  const e = action.event;
  switch (e.type) {
    case 'run_started':   return { ...state, runId: e.runId };
    case 'text_delta':    return { ...state, text: state.text + e.text };
    case 'tool_call':     return { ...state, toolCalls: [...state.toolCalls, { callId: e.callId, name: e.name, arguments: e.arguments }] };
    case 'tool_result':   return { ...state, toolCalls: state.toolCalls.map((t) => t.callId === e.callId ? { ...t, output: e.output, isError: e.isError } : t) };
    case 'run_completed': return { ...state, status: 'done' };
    case 'run_failed':    return { ...state, status: 'error', error: e.message };
  }
}

export function useAgentRun(conversationId: string) {
  const [state, dispatch] = useReducer(reducer, initial);
  const abortRef = useRef<AbortController | null>(null);
  const qc = useQueryClient();

  const start = useCallback(async (body: AgentRunRequest) => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    dispatch({ type: 'start' });
    try {
      await streamAgentRun(body, { signal: ac.signal, onEvent: (event) => dispatch({ type: 'event', event }) });
    } catch (err) {
      if (!ac.signal.aborted) dispatch({ type: 'fail', message: err instanceof Error ? err.message : 'Stream failed' });
    } finally {
      void qc.invalidateQueries({ queryKey: conversationKeys.detail(conversationId) }); // persisted messages
    }
  }, [qc, conversationId]);

  const stop = useCallback(() => abortRef.current?.abort(), []);
  useEffect(() => () => abortRef.current?.abort(), []);   // abort on unmount

  return { ...state, start, stop };
}
```

High token rates can cause one render per delta. If profiling shows jank, buffer deltas in a ref and flush on `requestAnimationFrame`. Render streamed Markdown with a sanitizing renderer; never `dangerouslySetInnerHTML` model output.

## 7. Reconnect and resume

For short runs (seconds to a couple of minutes), don't resume: on a drop, show "connection lost", then refetch the conversation — the server persisted whatever completed.

For long agent runs, decouple the run from the connection:

1. `POST /agent/runs` → `202` with `{ runId }`; the run executes in a worker (see other-patterns.md) and appends events to a store (Redis Stream, Postgres table) with sequence numbers.
2. `GET /agent/runs/{runId}/events` streams from the store; honor the `Last-Event-ID` header (or `?after=`) to replay missed events.
3. `POST /agent/runs/{runId}/cancel` stops it.

With cookie auth, step 2 can use native `EventSource`, which reconnects and sends `Last-Event-ID` automatically.

## 8. Infrastructure gotchas

- **Buffering proxies:** nginx buffers by default; `X-Accel-Buffering: no` (set above) or `proxy_buffering off;` on the location. Some CDNs and load balancers need streaming explicitly enabled.
- **Compression:** gzip middleware or proxy compression can hold bytes back. Exclude `text/event-stream`.
- **Idle timeouts:** load balancers often cut idle connections at 60s; the 15s heartbeat prevents that.
- **Vite dev proxy:** streams fine through `server.proxy`; if output arrives in bursts, check for compression middleware on the backend.
- **Workers:** each open stream holds a connection; async endpoints handle many concurrently, but size worker counts and LB connection limits for concurrent streams, not RPS.
- **HTTP/1.1 connection limit:** browsers allow ~6 connections per origin on HTTP/1.1; multiple long-lived `EventSource`s per tab can starve normal requests. Serve over HTTP/2 in production.

## 9. WebSockets

Use only when the client must send frequent messages during a live session. Keep the same discipline:

- Messages are discriminated unions of `ApiModel`s in both directions (`ClientMessage`, `ServerMessage`), added to `EXTRA_MODELS` for codegen.
- Authenticate during the handshake: cookies are sent automatically on same-origin; for bearer, send the token in the first message (not the URL), and close with code 4401 if invalid. Check the `Origin` header against an allow-list — CORS doesn't protect WebSockets.
- Heartbeat with ping/pong, reconnect with exponential backoff and jitter on the client, and resync state via a REST GET after reconnecting.
- Multiple backend instances need a pub/sub fan-out (Redis) to deliver messages to sockets on other instances.

```python
@router.websocket("/ws/sessions/{session_id}")
async def session_ws(ws: WebSocket, session_id: UUID):
    if ws.headers.get("origin") not in get_settings().allowed_ws_origins:
        await ws.close(code=4403); return
    user = await user_from_cookie(ws.cookies.get(SESSION_COOKIE))
    if user is None:
        await ws.close(code=4401); return
    await ws.accept()
    try:
        while True:
            msg = ClientMessage.model_validate_json(await ws.receive_text()).root
            async for out in handle(msg, user, session_id):
                await ws.send_text(out.model_dump_json(by_alias=True))
    except WebSocketDisconnect:
        pass
```
