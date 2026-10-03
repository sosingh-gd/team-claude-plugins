# Other Communication Patterns (apply when the project needs them)

## Contents
1. File uploads
2. File downloads and exports
3. Long-running jobs (202 + polling)
4. Idempotent retries
5. Optimistic updates
6. Concurrent edits (ETags)
7. Rate limits and backoff

## 1. File uploads

**Small files (≲ 10–20 MB) through the API:** multipart with `UploadFile`.

```python
@router.post("/{order_id}/attachments", response_model=AttachmentRead, status_code=201)
async def upload_attachment(order_id: UUID, file: UploadFile, service: AttachmentServiceDep):
    if file.content_type not in ALLOWED_TYPES:
        raise BusinessRuleError("Unsupported file type", code="unsupported_file_type")
    return await service.store(order_id, file)   # stream to storage in chunks; enforce max size while reading
```

Never trust the client's filename or content type: generate the storage key yourself, sniff the type, cap the size during the read (not after), and scan if users share files with each other.

Frontend: `openapi-fetch` needs a body serializer for multipart.

```ts
upload: (orderId: string, file: File) =>
  unwrap(api.POST('/api/v1/orders/{order_id}/attachments', {
    params: { path: { order_id: orderId } },
    body: { file } as never,           // generated type expects binary; FormData built below
    bodySerializer: () => { const fd = new FormData(); fd.append('file', file); return fd; },
  })),
```

Don't set `Content-Type` manually — the browser adds the multipart boundary. For progress bars, use `XMLHttpRequest` (`upload.onprogress`); `fetch` has no upload progress.

**Large files: presigned direct upload.** Keep bytes off the API servers.

1. `POST /uploads` with `{ filename, contentType, size }` → backend validates, returns `{ uploadId, url, fields | headers }` (S3/GCS/Azure presigned).
2. Browser uploads straight to storage.
3. `POST /uploads/{uploadId}/complete` → backend verifies the object exists and matches, then links it to the domain entity.

## 2. File downloads and exports

```python
@router.get("/{order_id}/invoice.pdf", response_class=StreamingResponse,
            responses={200: {"content": {"application/pdf": {}}}})
async def download_invoice(order_id: UUID, service: InvoiceServiceDep):
    stream, filename = await service.render_pdf(order_id)
    return StreamingResponse(stream, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

- With cookie auth, a plain `<a href="/api/v1/orders/…/invoice.pdf">` works and is the simplest download.
- With bearer auth, fetch as a blob (`parseAs: 'blob'` in openapi-fetch), then `URL.createObjectURL` + a temporary `<a download>`; revoke the URL afterwards.
- Stored files: redirect (`307`) to a short-lived presigned URL instead of proxying bytes.
- Big CSV exports: use a job (section 3) that produces a file, then download it.

## 3. Long-running jobs (202 + polling)

Anything that may exceed a few seconds (reports, imports, bulk operations, long agent runs) becomes a job resource.

```python
class JobRead(ApiModel):
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float | None = None          # 0..1
    result_url: str | None = None
    error: ProblemDetail | None = None

@router.post("/exports", status_code=202, response_model=JobRead)
async def start_export(body: ExportRequest, response: Response, jobs: JobServiceDep, user: CurrentUser):
    job = await jobs.enqueue("export_orders", body, user)
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    return job

@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: UUID, jobs: JobServiceDep, user: CurrentUser): ...
```

Worker choice: `arq` or `taskiq` (async, Redis) for async codebases; Celery/Dramatiq if already in the stack. FastAPI's `BackgroundTasks` is only for small fire-and-forget work (send an email after responding) — it dies with the process and has no retries or status.

Frontend polling stops itself when the job finishes:

```ts
export function useJobQuery(jobId: string | undefined) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/jobs/{job_id}', { params: { path: { job_id: jobId! } }, signal })),
    enabled: !!jobId,
    refetchInterval: (q) => (['queued', 'running'].includes(q.state.data?.status ?? 'queued') ? 2000 : false),
  });
}
```

Upgrade to SSE (`GET /jobs/{id}/events`) only if progress needs to feel live.

## 4. Idempotent retries

For POSTs that create things or move money, accept an `Idempotency-Key` header (client-generated UUID per user action, reused on retry). Store key → response for ~24h; on repeat, return the stored response. This makes "network failed, user clicked again" safe.

```ts
const key = useMemo(() => crypto.randomUUID(), []);   // one per form instance / action
api.POST('/api/v1/payments', { body, headers: { 'Idempotency-Key': key } });
```

## 5. Optimistic updates

Use for small, likely-to-succeed edits (toggle, rename, reorder). Roll back on error.

```ts
useMutation({
  mutationFn: (status: OrderStatus) => ordersApi.update(id, { status }),
  onMutate: async (status) => {
    await qc.cancelQueries({ queryKey: orderKeys.detail(id) });
    const previous = qc.getQueryData<Order>(orderKeys.detail(id));
    qc.setQueryData<Order>(orderKeys.detail(id), (o) => (o ? { ...o, status } : o));
    return { previous };
  },
  onError: (_e, _v, ctx) => ctx?.previous && qc.setQueryData(orderKeys.detail(id), ctx.previous),
  onSettled: () => qc.invalidateQueries({ queryKey: orderKeys.detail(id) }),
});
```

## 6. Concurrent edits (ETags)

When two users can edit the same record, include a `version` (integer, incremented on write) in the read schema, send it back on update (`If-Match` header or a body field), and return `409` with `code: "version_conflict"` if it changed. The UI then refetches and shows a "changed by someone else" message instead of silently overwriting.

## 7. Rate limits and backoff

Return `429` as Problem Details with a `Retry-After` header. TanStack Query's default retry policy above doesn't retry 4xx; handle 429 explicitly where it matters (respect `Retry-After`), and use `slowapi` or the gateway for enforcement.
