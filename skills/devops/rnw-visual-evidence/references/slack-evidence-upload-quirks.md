# Delivering evidence files into a Slack thread — API quirks that silently lose artifacts

Verified 2026-10-25 while attaching PR #283/#277 before/after evidence to a live thread.
The user-owned skill `evidence-attach-to-slack` documents the 3-stage flow; these are the
failure modes it does not cover, each of which cost a retry loop.

## 1. `files.getUploadURLExternal` must be form-encoded

Sending JSON returns a misleading error that claims the fields are missing:

```json
{"ok": false, "error": "invalid_arguments",
 "response_metadata": {"messages": ["[ERROR] missing required field: length",
                                    "[ERROR] missing required field: filename"]}}
```

Both fields were present in the JSON body. Fix: `curl -F` or
`urllib.parse.urlencode({...}).encode()` with
`Content-Type: application/x-www-form-urlencoded`. Only stages 2 and 3 take JSON.

## 2. `completeUploadExternal` with `thread_ts` + `initial_comment` can silently drop files

Observed pattern across 12 files: stage 3 returned `{"ok": true, "files": [...]}` for every file,
but only some produced a thread message. The reliable split:

| file kind | `channel_id` + `thread_ts` + `initial_comment` | `channel_id` + `thread_ts`, no comment |
|---|---|---|
| PNG (hosted image) | landed | landed |
| small `.json` (snippet) | landed | landed |
| `.mp4` / larger docs | **`ok: true`, no message** | **landed** |

Fix that worked: upload one file per call, pass **only** `channel_id` + `thread_ts`, then post one
separate plain-text summary message listing names + sha256. Do not batch 12 files into a single
`files: [...]` with a long `initial_comment`.

## 2a. `alt_txt` in stage 1 makes stage 3 report success on an UNSHARED file (verified 2026-10-25)

This is worse than §2 because nothing errors: stage 3 returns `ok: true` with a real `file_id`, the
file exists, and it is **not shared into any channel** — the user sees no file and you look like you
invented the attachment.

```python
# BAD: alt_txt present -> file uploads, stage 3 ok:true, shares:[] channels:[]
q = urlencode({"filename": name, "length": len(raw), "alt_txt": name}).encode()
# GOOD: no alt_txt, channel_id only -> shares:['public'], channels:['<C...>']
q = urlencode({"filename": name, "length": len(raw)}).encode()
```

Also observed in the same account: `completeUploadExternal` with `channel_id` + `thread_ts` produced
**no** share (files landed unshared), while `channel_id` alone shared correctly — the trade-off is that
the file posts to the channel, not into the thread. Say which one you got.

**Verification that actually decides it** (per file, not per batch):

```bash
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/files.info?file=F0XXXX" \
  | python3 -c 'import sys,json;f=json.load(sys.stdin)["file"];print(f["name"],f["size"],list(f.get("shares",{})),f.get("channels"),f.get("permalink"))'
```

`shares` must be non-empty and `permalink` non-null before you write "attached". Compare against a file
the user already confirmed (its `shares` keys and `channels` list are the reference shape). Uploading
with `channel_id` also gives you a stable permalink per artifact — quote file ID + permalink + sha256 in
the summary.

If you already told the user a file was attached, **retract by name** (state the file was never shared,
name the mechanism, quote the corrected `shares` evidence) rather than re-uploading silently.

## 3. Verify against the raw API, not the MCP wrapper

`mcp__slack__conversations_replies` rendered `FileCount 0` / no file rows while
`conversations.replies` over HTTP showed the file-bearing messages. Always confirm with:

```bash
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/conversations.replies?channel=<C>&ts=<thread_ts>&limit=40" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);[print(m["ts"],[f["name"] for f in (m.get("files") or [])]) for m in d["messages"]]'
```

Count expected vs delivered names before telling the user "attached".

## 4. Retrieving files the user attached

```bash
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/files.info?file=F0XXXX" | jq -r .file.url_private_download
curl -sL -H "Authorization: Bearer $SLACK_BOT_TOKEN" "<url_private_download>" -o local.bin
sha256sum local.bin    # must equal the sha256 the user stated
```

Re-hash every delivered artifact and compare against the user's stated SHA before reviewing it —
byte identity is the cheapest way to answer "are these the same clips you already reviewed?".

## 5. Token choice

Bot token (`xoxb`) uploads land as the bot; a user token (`xoxp`) posts as the human. A token that
lacks `files:write` returns `missing_scope` on stage 1 — that is a scope problem, not a recipe
problem. Never paste a token value into chat or a receipt.
