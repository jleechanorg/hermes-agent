# Publication share, ownership, and config claims (2026-10-25)

Three claims that were reported as facts and were not. Same underlying error in each: an *ack* was
treated as a *receipt*.

## 1. "Attached" vs actually shared (Slack files API)

Incident: a review reply stated two `.webm` clips and five JSON receipts were attached to a thread.
The reviewer re-read the thread metadata and found only three PNGs. Re-verification confirmed it:

```
files.info?file=F0CBW32UB70  → name after-0c9201f9-transcript.png, shares ['public'], channels ['C0C7SF0S4JH']
files.info?file=F0CBW32UB70… (the claimed webms/JSONs)  → no such shared file
```

Root cause, reproduced deliberately:

| stage-1 params | stage-3 params | `ok` | `files.info` |
|---|---|---|---|
| `filename`+`length`+`alt_txt` | files + `channel_id` + `thread_ts` | true | `shares: []`, `channels: []` |
| `filename`+`length` | files + `channel_id` + `thread_ts` | true | `shares: []`, `channels: []` |
| `filename`+`length` | files + `channel_id` only | true | `shares: {'public': …}`, `channels: ['C0C7…']`, `permalink` set |

Two silent-unshare triggers: `alt_txt` on `files.getUploadURLExternal`, and `thread_ts` on
`files.completeUploadExternal`. Both return success; neither shares. Consequences: files that were
uploaded are invisible to the user, and any "see attached" sentence is false.

Gates:

```python
# after completeUploadExternal, for EVERY file
info = files_info(file_id)
assert info["shares"] and channel_id in (info.get("channels") or []), "unshared upload"
record = {"name": …, "bytes": len(raw), "sha256": sha256(raw), "file_id": file_id,
          "permalink": info["permalink"]}
```

- Verify the thread too when thread placement is claimed: `conversations_replies` →
  `FileCount` / `AttachmentIDs` per message. A channel-level share is verifiable; a thread-intended
  share that silently fell back to unshared is not.
- Never paraphrase a report from the filenames you passed into code. The list of names in the script
  is not evidence of delivery.
- Reusable runner: `scripts/slack_upload_verified.py`.

## 2. `git blame` is authorship, not custody

A question was "who is the source owner of the creation/seed domain?" and the answer given was
`git blame -L 8900,8930 → 31/31 lines authored by <user>`, presented as the owner of record. Correct
parts: that file/function is where `seed-prompt-{i}` / `seed-reply-{i}` are written, and there is a
single writer. Wrong part: authorship metadata is not a live owner/custody receipt, and there is no
`CODEOWNERS` in the repo (`find . -maxdepth 3 -name CODEOWNERS` → empty).

Report shape that survives review:

```
de facto authorship: <file>:<def line> (blame range, all lines one author)
declared registry:   none — no CODEOWNERS in repo
live custody:        <incumbent accepted / not accepted> (needs their own statement)
writers:             one producer of <id scheme> at <file>:<line>; deferred/atomic branch writes
                     <scheme A>, synchronous fallback can write ordinary ids
```

Consequence rule: with no declared owner and no acceptance, do not patch that domain, do not migrate
data, and do not add a competing writer — hand back and wait for the incumbent.

## 3. Bypass-off is a deployed-config fact, not a request-header fact

Reported: "every `/api/` request carried `Authorization`, zero bypass headers → backend bypass-off."
Correction: that shows only what *our client* sent. The config fact comes from the revision:

```bash
gcloud run services describe <svc> --region <r> --format=json \
  | jq -r '.spec.template.spec.containers[0].env[] | "\(.name)=\(.value // .valueFrom)"'
gcloud run services describe <svc> --region <r> \
  --format='value(status.latestReadyRevisionName,spec.template.spec.containers[0].image)'
```

Findings worth stating explicitly, in both directions:

- absent vars (`TESTING_AUTH_BYPASS`, `ALLOW_TEST_AUTH_BYPASS`, `MOCK_SERVICES_MODE`, `TEST_MODE`,
  `USE_MOCK_FIREBASE`) → *name them as absent*, do not infer from headers;
- a bypass-ish capability that **does** exist in config but was not exercised (header-gated smoke
  token: `ENVIRONMENT ∈ {dev, preview}` + `X-MCP-Smoke-Token`) → "present, unused by our requests";
- environment labels that shape the verdict (`ENVIRONMENT=dev` while `FLASK_ENV=production`).
- identity binding: prove the backend served the account's own data (`/api/campaigns/<id>` response
  contains the resolved uid) rather than only that a token was sent.

## 4. Mint accounting when a session is reused

A contract run needed an ID token. It reused the persisted Firebase SDK session (default app, SDK
`LOCAL` persistence, originally established by `signInWithCustomToken`) to call
`currentUser.getIdToken()` in-page, then passed the token to the harness in-memory. That is **not** a
new mint: report "session reused, mint count unchanged (2/3)", keep the token out of argv, console,
receipts and HAR, and state separately whether the harness verified served identity (it declared
`served_identity_verified: false` — operator-declared revisions only).

## 5. Pagination caveat for "does a record exist?" searches

When searching a paginated history for a marker id (e.g. `seed-prompt-0`), the first returned row is
often the **newest window boundary**, not campaign/collection start. In 40 sampled campaigns, 23 first
windows carried `has_older: true`, and the only real marked row appeared only after paging older
(`/story?before_id=…`). Reporting "no such record" from the first page is a false negative; state
pages fetched, boundary windows, and the paging cursor used.
