# Streaming: SSE for Chat and Agents, WebSockets When Needed

## Contents
1. Start here: the simplest working chat
2. Choosing a transport
3. Typed event contract
4. Backend: the SSE response
5. Heartbeats, disconnects, and resources
6. Optional: tool calls and agent steps
7. Optional: reconnect and resume long runs
8. Infrastructure gotchas
9. WebSockets

Sections 1–5 are what a chat screen needs. Sections 6 and 7 are **optional**: add them only when the UI really shows tool calls, or runs last long enough that a page refresh must reattach to them.

## 1. Start here: the simplest working chat

Three defaults keep chat code small. Follow them unless the project has a concrete reason not to.

1. **Create the conversation first, then stream into it.** `POST /conversations` returns the new conversation's id. Only then does the frontend call `POST /conversations/{id}/messages/stream`. The frontend always knows which conversation it is in, so it never has to change the URL halfway through a stream or check whether a stream still belongs to the current screen.
2. **Write the streamed text into the cached conversation.** The conversation is a normal TanStack Query query. While the reply streams, append each piece of text to the last message in that cached data; when the reply ends, refetch. There is one list of messages, not a server copy plus a streaming copy to merge.
3. **The stream function takes `onText`, resolves when done, and throws on failure.** The caller needs one `try/catch`, not an event handler spread across a hook.

The templates `backend/agent/*` and `frontend/chat/*` implement exactly this, and work end to end as is (the backend echoes the message back until you plug in an LLM).

### Backend

```python
# app/features/agent/router.py (shape; full version in the template)
router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(agent: AgentServiceDep) -> ConversationRead:
    return agent.create_conversation()


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(conversation_id: str, agent: AgentServiceDep) -> ConversationRead:
    return agent.get_conversation(conversation_id)


@router.post("/{conversation_id}/messages/stream", response_class=EventStreamResponse, responses=...)
async def stream_reply(conversation_id: str, body: SendMessageRequest, request: Request, agent: AgentServiceDep):
    agent.get_conversation(conversation_id)       # 404 as normal Problem Details, before streaming starts
    async def events():
        async for item in with_heartbeat(agent.reply(conversation_id, body.content), interval=15):
            if await request.is_disconnected():
                break
            yield item if isinstance(item, str) else format_sse(item)
        # the template also catches errors and sends run_failed (section 4)
    return EventStreamResponse(events())
```

```python
# app/features/agent/service.py (shape)
async def reply(self, conversation_id: str, content: str) -> AsyncIterator[ApiModel]:
    save the user message
    async for chunk in llm.stream(...):           # your LLM SDK
        yield TextDeltaEvent(text=chunk.text)
    save the assistant message
    yield RunCompletedEvent(message_id=message.id)
```

The service saves both messages, so refetching the conversation after the stream returns the real, saved versions.

### Frontend: the stream function

```ts
// features/chat/chat.api.ts (excerpt)
export async function streamReply(
  conversationId: string,
  content: string,
  { signal, onText }: { signal: AbortSignal; onText: (text: string) => void },
): Promise<void> {
  const res = await fetch(`${env.apiBaseUrl}/api/v1/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authHeaders('POST') },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok || !res.body) throw await ApiError.fromResponse(res);

  let completed = false;
  let failure: string | undefined;
  const parser = createParser({
    onEvent(msg) {
      const event = JSON.parse(msg.data) as AgentEvent;
      if (event.type === 'text_delta') onText(event.text);
      if (event.type === 'run_completed') completed = true;
      if (event.type === 'run_failed') failure = event.message;
    },
  });

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.feed(value);
  }
  if (failure) throw new Error(failure);
  if (!completed && !signal.aborted) throw new Error('The connection dropped before the reply finished');
}
```

It uses `fetch` rather than `EventSource` because `EventSource` can't send a POST body. It bypasses openapi-fetch, so it adds `authHeaders()` from `lib/http.ts` itself.

### Frontend: one hook for the screen

```ts
// features/chat/useChat.ts
export function useChat(conversationId: string) {
  const queryClient = useQueryClient();
  const conversation = useConversationQuery(conversationId);
  const [isReplying, setIsReplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []); // stop streaming when the screen closes

  async function send(content: string) {
    const key = conversationKey(conversationId);
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setIsReplying(true);

    // Show the user's message and an empty reply right away; the stream fills the reply in.
    await queryClient.cancelQueries({ queryKey: key });
    queryClient.setQueryData<Conversation>(key, (old) =>
      old && { ...old, messages: [...old.messages,
        { id: 'pending-user', role: 'user', content },
        { id: 'pending-reply', role: 'assistant', content: '' }] },
    );

    try {
      await streamReply(conversationId, content, {
        signal: controller.signal,
        onText: (text) =>
          queryClient.setQueryData<Conversation>(key, (old) =>
            old && { ...old, messages: old.messages.map((m) =>
              m.id === 'pending-reply' ? { ...m, content: m.content + text } : m) },
          ),
      });
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setIsReplying(false);
      void queryClient.invalidateQueries({ queryKey: key }); // swap the pending messages for the saved ones
    }
  }

  return { messages: conversation.data?.messages ?? [], isLoading: conversation.isLoading,
           isReplying, error, send, stop: () => abortRef.current?.abort() };
}
```

### Frontend: the screen

```tsx
// "New chat" creates the conversation, then navigates to it.
const createConversation = useCreateConversationMutation();
const startChat = () => createConversation.mutate(undefined, { onSuccess: (c) => navigate(`/chat/${c.id}`) });

// The page gives the screen a key, so switching conversations starts with fresh state.
export function ChatPage() {
  const { conversationId = '' } = useParams();
  return <ChatScreen key={conversationId} conversationId={conversationId} />;
}

function ChatScreen({ conversationId }: { conversationId: string }) {
  const { messages, isReplying, error, send, stop } = useChat(conversationId);
  // render messages, a composer that calls send(text), a Stop button while isReplying, and error
}
```

That is the whole feature: `chat.api.ts`, `useChat.ts` and the components. Render model output with a sanitizing Markdown renderer; never `dangerouslySetInnerHTML`. If very fast streams make the UI stutter, collect text in a ref and write it to the cache once per animation frame, but only after you see the problem.

## 2. Choosing a transport

| Need | Use |
|---|---|
| Server → client stream started by a request (chat replies, agent steps, progress) | **SSE over `fetch` POST** (section 1) |
| Server → client notifications on a long-lived channel (job finished, new message) with cookie auth | SSE via `EventSource` GET (auto-reconnect built in) |
| Status of a job that takes minutes | Polling with TanStack Query `refetchInterval` (other-patterns.md) — simplest, cache-friendly |
| Bidirectional, low latency, client sends many messages mid-stream (collaborative editing, voice, games) | **WebSocket** (section 9) |

## 3. Typed event contract

The stream is a discriminated union of `ApiModel`s; the `type` field tells the event kinds apart on both sides.

```python
# app/features/agent/events.py
class TextDeltaEvent(ApiModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class RunCompletedEvent(ApiModel):
    type: Literal["run_completed"] = "run_completed"
    message_id: str


class RunFailedEvent(ApiModel):
    type: Literal["run_failed"] = "run_failed"
    code: str
    message: str


AgentEventUnion = Annotated[TextDeltaEvent | RunCompletedEvent | RunFailedEvent, Field(discriminator="type")]


class AgentEvent(RootModel[AgentEventUnion]):
    """Every SSE `data:` payload is one of these."""
```

Register it for codegen: in `app/scripts/export_openapi.py`, `EXTRA_MODELS = [AgentEvent]`. After `make api`, the frontend has `components['schemas']['AgentEvent']` as a TypeScript union. This relies on `json_schema_serialization_defaults_required=True` in `ApiModel` (backend-structure.md); without it the defaulted `type` field is generated as optional and TypeScript can't tell the events apart.

Every stream ends with exactly one `run_completed` or `run_failed`. The client treats a stream that closes without one as a dropped connection.

Add more event types only when the UI uses them (section 6).

## 4. Backend: the SSE response

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

Errors before the stream starts (validation, auth, unknown conversation) return normal Problem Details with a 4xx status. Once the 200 and headers are sent, errors can only be reported as a `run_failed` event, so the endpoint wraps the loop:

```python
async def events():
    try:
        async for item in with_heartbeat(agent.reply(conversation_id, body.content), interval=15):
            ...
    except asyncio.CancelledError:
        raise                                  # client went away; let cleanup run
    except Exception:
        logger.exception("reply failed")
        yield format_sse(RunFailedEvent(code="reply_failed", message="The assistant could not reply"))
```

The service turns whatever LLM SDK or agent framework the project uses into these event types, so the frontend doesn't change if the provider does.

## 5. Heartbeats, disconnects, and resources

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
- **Don't hold a request-scoped DB session for the whole stream.** Streams can last minutes. Inside the service, open short sessions via `session_factory()` for each write (save the user message, save the reply).
- **Persist as you go** if partial output matters: save the final assistant message (or checkpoints) server-side, so a page refresh can load it via a normal GET.

## 6. Optional: tool calls and agent steps

Skip this section for plain chat. Use it when the UI must show what an agent is doing (tool calls with their inputs and results, step lists).

Add the event types:

```python
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
```

Keep the section 1 shape (create first, one `try/catch`), and give the stream function one more callback, `onToolCall` / `onToolResult`, rather than switching to a general `onEvent`. Show tool activity in a small `useState` list next to the cached messages, and clear it when the reply finishes and the conversation is refetched. If the server saves tool calls as part of the message, render them from the refetched conversation instead.

A `useReducer` that accumulates the whole run is the right tool only for streams that are **not** chat: a progress view for a long job, or a one-off generation that isn't saved as a conversation. In that case keep the reducer state as the only copy of the data and don't mix it with cached messages.

## 7. Optional: reconnect and resume long runs

For short replies (seconds to a couple of minutes), don't resume: on a drop, show "connection lost" and refetch the conversation, which contains whatever the server saved.

Only for long agent runs that must survive a page refresh, separate the run from the connection:

1. `POST /conversations/{id}/runs` → `202` with `{ runId }`; the run executes in a worker (see other-patterns.md) and appends events to a store (Redis Stream, Postgres table) with sequence numbers.
2. `GET /runs/{runId}/events` streams from the store and honors the `Last-Event-ID` header (or `?after=`) to replay missed events.
3. `POST /runs/{runId}/cancel` stops it.

With cookie auth, step 2 can use native `EventSource`, which reconnects and sends `Last-Event-ID` automatically. The run id comes back from step 1, before any streaming, so the frontend still never learns an id partway through a stream.

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
