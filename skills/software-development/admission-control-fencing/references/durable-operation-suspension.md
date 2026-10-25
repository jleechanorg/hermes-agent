# Durable operation across client suspension — worked example (2026-10-25)

Two PRs implementing "portrait generation must work even if the user tabs away":
`worldai_frontend` #292 (client) and `worldarchitect.ai` #10866 (server record). Numbers below are
measured, not projected; use them to sanity-check a new implementation.

## The bug being fixed

`POST /api/portrait/generate` is a synchronous ~140 s request. The client sent it with a 140 s
`AbortController` timeout and nothing else: no operation id, no durable result, no status read. A
frozen or discarded page loses a generation the user already paid for, and the only recovery the UI
offers is Retry — a second paid generation.

## Server contract that worked

```
POST /api/portrait/generate           optional operation_id (^[0-9a-fA-F-]{36}$; malformed -> 400)
  first sight                          run + persist + respond as legacy
  duplicate while pending              202 {"success": false, "pending": true, "operation_id": ...}
  duplicate after succeeded            200 cached body, zero provider calls
  duplicate after failed               stored error, zero provider calls
  materially different repeat          409 (never silent reuse)
  no operation_id                      legacy path byte-for-byte
GET /api/portrait/operations/<id>      {"status": "pending"|"succeeded"|"failed", ...body}
                                       404 unknown OR other-user; @check_token guard
retention                              24 h record TTL + 660 s pending lease
```

Single-flight was an atomic Firestore `create` on the record key — a concurrent duplicate loses the
race and gets `202`. That is proven against the fake store's `create` semantics plus one real thread;
it is **not** proof for multi-instance Cloud Run contention, and the report said so.

## Storage sizes (the part that breaks implementations)

| measurement | value |
|---|---|
| decoded 2K portrait | 1,017,231 B |
| base64 in one Firestore doc | ~1.36 MB |
| payload that persisted | 400 KB |
| payload rejected | 1.6 MB → `InvalidArgument: 400 Property payload contains an invalid nested entity` |

First implementation stored the body inline and therefore reddened in the DEFAULT delivery mode: the
record ended non-replayable and the client was told the result "could not be retained for replay".
The evidence clip only passed because it ran `ENVIRONMENT=preview` (URL delivery) with a pinned
`image_provider_preference` — a real example of an evidence run that silently dodged the failing path.

Fix: object blob at `portrait_operations/<user_id>/<operation_id>.json`, `content_type=application/json`,
private (never `make_public()`); Firestore keeps `payload_blob_path`, `payload_bytes`,
`payload_sha256`, `payload: null`; replay re-reads and sha256-verifies, then serves those exact bytes.
Blob write precedes the terminal write, so an object-store failure records terminal
`failed` / `operation_persist_failed` while the first caller still receives its image.

## Client shape

- `src/services/portraitOperations.ts`: `begin(payload)` persists
  `{operationId, payload, campaignId, createdAt}` **before** sending, `settle`, `pending`, `clear`.
- `src/services/appForeground.ts`: one platform-neutral resume signal (`AppState` → active on native,
  `visibilitychange` → visible on web).
- Resume: `GET /operations/<id>`; `succeeded` → hydrate and clear; `pending` → keep the in-progress UI
  and poll with bounded backoff **only while foregrounded**; `failed` → error + the existing Retry.
- Feature detection: `404`/`405` from the operations endpoint degrades to today's single POST without
  surfacing a capability error — needed because the client ships before the backend is deployed.
- Retry mints a new operation id; nothing else may mint one.

## Test/receipt shape that satisfied review

Backend (`50 passed` at `a4daf2e3`): `>1 MiB` payload round-trip with byte-identical replay, blob-write
failure → terminal `failed`, duplicate-while-pending → `202` with one provider call, `409` on
mismatched body, legacy path unchanged. Provider mocked throughout; no paid calls in unit tests.

Frontend (`24 passed` across 3 new suites): tab-away → resume → result recovered with **one** generation
request; pending poll; failure path; feature-detection fallback; no duplicate operation ids.

Two limitations worth copying into any report of this kind: the client lane could not reach a real
`visibilityState='hidden'` on this host (see `browser-evidence-harness-integrity`), and the "backend
cannot answer for a persisted operation" case necessarily shows Retry — which is a second paid
generation. That is a product decision, not a code decision: state the recommendation, don't bury it.
