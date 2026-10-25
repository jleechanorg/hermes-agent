# Evidence packet remediation — repairing a published packet a reviewer rejected

Source: `jleechanorg/worldai_frontend` PR #160 (bottom composer spinner), 2026-10-24. A reviewer audited
the published mobile-web before/after packet and rejected six items. Nothing was re-run: no browser, no
token mint, no gameplay, no second operator. Every repair below is a **re-derivation from a retained
original**.

## The audit findings and what each one actually was

| Finding | Root cause | Repair |
|---|---|---|
| `backend_requests.status` = `"->"`, `bytes` = `"401"` | positional index shift in the summariser | re-derive with the correct indices |
| `stream_detected: false`, unexplained | buffering evidence proxy | replace with a `stream` block naming the cause |
| no build / served-bundle / auth / proxy records | packet shipped only summaries | recover into `originals/` + `INDEX.json` |
| `/__whoami` payload missing | consumed in-process, never written | carry logged fields, `payload_was_persisted: false` |
| manifest self-checksum | `SHA256SUMS.txt` listed itself | drop self-entry, publish hash out-of-band |
| absolute home path + campaign id | no sanitization pass | label + sha256 prefix, `<home>` placeholders |
| **custom-token auth presented as real sign-in** | wrong evidence class | reclassify **supplementary**; primary lane stays OPEN |

## 1. The parser defect (worked example)

Harness line format and the recorded mis-parse:

```
PROXY GET /api/settings -> 401 bytes=32
      [0]  [1] [2]          [3] [4] [5]

v1:  status = parts[3]  -> "->"      bytes = parts[4] -> "401"
v2:  status = parts[4]  -> 401       bytes = parts[5] -> "32"
```

```python
def backend_summary_fixed(path):
    count, statuses, sample = 0, {}, []
    with open(path) as fh:
        for line in fh:
            if not line.startswith("PROXY"):
                continue
            parts = line.split()
            if len(parts) < 6:            # refuse to guess on a short line
                continue
            count += 1
            status = parts[4]
            statuses[status] = statuses.get(status, 0) + 1
            sample.append({"method": parts[1], "path": parts[2],
                           "status": int(status), "bytes": int(parts[5].replace("bytes=", ""))})
    return {"count": count, "statuses": statuses, "sample": sample}
```

Repaired ledger, and the invariant that proves the repair touched only two fields:

| Side | Requests (unchanged) | 200 | 401 | 429 |
|---|---|---|---|---|
| BEFORE | 24 | 21 | 2 | 1 |
| AFTER | 18 | 11 | 0 | 7 |

The AFTER take's seven `429`s on `/api/settings` are genuine shared-dev-tier rate limiting;
`/api/campaigns` and the interaction stream still returned 200. Disclose it — do not report "all 200".

## 2. Why `stream_detected` was false (and why you still must not claim streaming)

Two independent facts, both checkable from the retained rig:

- The sentinel exists: `src/components/MessageBubble.tsx:158` renders `testID="message-streaming-tail"`.
- The transport cannot deliver chunks: `proxy.py:63-82` does `payload = resp.read()` on the upstream
  response and then sends it with an explicit `Content-Length`. The SSE body is buffered and replayed
  whole, so the browser never receives partial bytes and the tail element cannot appear during sampling.

Consequence stated in the packet: the clips prove **pending→settle UI states**, not token-by-token
streaming. A streaming claim needs a passthrough proxy that preserves chunking — a different capture.

Receipt shape that replaces the bare boolean:

```json
"stream": {
  "client_stream_tail_observed": false,
  "stream_endpoint_requests": [{"method": "POST", "path": "/api/campaigns/campaign-A/interaction/stream",
                                "status": 200, "bytes": 92943}],
  "sentinel_testid_exists_in_app": true,
  "sentinel_testid_source": "src/components/MessageBubble.tsx:158",
  "why_false": "the evidence proxy buffers the upstream body (proxy.py:63-82) ...",
  "consequence": "proves pending->settle states, NOT token-by-token streaming"
}
```

## 3. Recovering originals (what to carry, and the provenance record)

Carried: `capture-logs/` (the harness's own log, take block cited by start line), `proxy-logs/`
(per-request ledger; the harness truncates it per run, so each file *is* that take), `build/`
(export + npm logs, harness run output), `rig/` (harness + proxy source — the reader needs it to verify
§1 and §2), `auth/` (mint script + a derived auth record; no token, no uid).

`originals/INDEX.json` per file: `original_sha256`, `sanitized_sha256`, `bytes`, `redaction` note. That
pair is what makes sanitization auditable — a reader can confirm the sanitized copy came from a specific
original without you publishing the original.

When a payload was never persisted, say so in the artifact:

```json
{"recovered_from": "originals/capture-logs/capture-base.log:79",
 "payload_was_persisted": false,
 "note": "the /__whoami JSON body was consumed in-process and never written to disk; only these four fields survive",
 "logged_fields": {"sha_prefix": "...", "side": "...", "bundle": "...", "bundle_sha256_prefix": "..."}}
```

Substitute verification where recovery is impossible: re-compute the served-bundle sha256 from the
retained export tree and label it "fresh re-computation, not an original trace". It matched the
in-process assertion (`0c2b4a07…` / `022eca2d…`), which is the strongest honest statement available.

## 4. Auth classification — the item that changed the verdict

Path in full (`auth/mint_token.py`, harness sign-in block):

1. Admin service account → `firebase_admin.auth.create_custom_token(uid)` for the dedicated test account.
2. Page loads the official Firebase JS SDK and calls `signInWithCustomToken(token)`.
3. SDK writes its own persistence; a fresh page lets the app's own SDK restore the session.
4. `/api/*` then carries a real ID token → backend enforcement visible: anon `401`, authed `200`.

Repo rule (`.claude/skills/evidence-standards.md`): `:17` forbids "auth bypass or injected
tokens/state"; `:21` makes "synthetic sign-in" supplementary, unable to carry `/es`/`/er` PASS or visual
acceptance. An admin-minted custom token is an injected token ⇒ **supplementary**.

Write both halves in the packet: what is real (tier, enforcement, account, campaign, renderer) and what
is not (the sign-in path). Then keep the primary lane open and name the two legitimate closers: a
genuine end-user sign-in capture, or an explicit PR-scoped operator waiver.

## 5. Manifest, redaction, and publication

```bash
# manifest: relative paths, never itself
python3 regen_manifest.py            # walks packet root, skips SHA256SUMS.txt, prints its own sha256
shasum -a 256 -c SHA256SUMS.txt | grep -vc ': OK'   # expect 0

# leak scan (the scan line must not quote the secret it is scanning for)
grep -rIl "<campaign-id>\|<uid>\|/Users/<user>" . ; echo "EXIT:$? (1 = no hits)"

# publish v2 beside v1, then verify 200 + byte-identical sha256
gcloud storage cp -r "$PKT"/* "$NEW_PREFIX/"
for f in README.md REMEDIATION.md SHA256SUMS.txt receipt-base.json receipt-cand.json *.mp4; do
  code=$(curl -s -o /tmp/dl -w '%{http_code}' "$HTTP_BASE/$f")
  [ "$code" = 200 ] && cmp -s /tmp/dl "$PKT/$f" && echo "OK $f" || echo "FAIL $f"
done
```

Redaction scheme that keeps the audit answerable: `campaign-A…D` labels **plus** a 12-hex sha256 prefix
of the id (same prefix on both receipts ⇒ same campaign, proven without publishing it); `<home>`,
`<capture-workdir>`, `<export-root:side>` placeholders; uid reduced to a hash prefix + `has_email` +
`providers` + `disabled`.

Old prefix: upload `SUPERSEDED.md` enumerating each defect and its cause. Leave the defective bytes in
place — that copy *is* the audit record. Do not "fix" it in place and do not delete it.

## 6. Full-video review support

```bash
# 1 Hz, full-coverage contact sheet (64 tiles); -f image2 is required or the
# output filename alone selects an MP4 container and you ship a mislabeled video
ffmpeg -i in.mp4 -vf "fps=1,scale=120:-1,tile=8x8" -frames:v 1 -f image2 sheet.png
file sheet.png   # expect: PNG image data, 960 x 2080
```

The sheet is tooling for the reviewer, not a claim that continuous review happened. Keep
"present, not exercised" for controls that were never clicked (Cancel, Undo) and say plainly that
sampled frames are not a full playback review.

## Reply shape that survived this audit

Lead with the verdict change, not the formatting fixes: "the repair changed the verdict — this packet
cannot close the primary visual lane." Then root cause → prevention → fix → proof, with the recovered
original, the repaired numbers, the invariant that proves it is a repair, the published v2 URL, the
manifest's own sha256, and one line per item still unproven.
