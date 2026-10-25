# Correction log — token name and upload verification (2026-10-25)

## 1. Token variable renamed; the SKILL.md body is stale

SKILL.md's "Token source" section still names `OPENCLAW_SLACK_BOT_TOKEN`. Those names were
**retired 2026-07-04**. The live variables in `~/.bashrc` are:

```
1000:export SLACK_BOT_TOKEN="xoxb-…"
1005:export HERMES_SLACK_BOT_TOKEN="xoxb-…"
```

`~/.profile` also carries `SLACK_BOT_TOKEN`, `SLACK_MCP_XOXB_TOKEN`, `SLACK_APP_TOKEN`, and a
user-token `SLACK_USER_TOKEN` (`xoxp-…`) that is NOT the bot upload identity.

A script that only greps `^export OPENCLAW_SLACK_BOT_TOKEN=` fails with "token not found" even
though uploads work. Resolve in this order: `SLACK_BOT_TOKEN` → `HERMES_SLACK_BOT_TOKEN` →
`OPENCLAW_SLACK_BOT_TOKEN` (legacy), and require the `xoxb-` prefix.

SKILL.md itself could not be patched: `skill_manage(action='patch')` rejects any write to this
skill with "Description exceeds 1024 characters" (the frontmatter description is long, and the
validator re-checks it on every write). Fix the frontmatter description length before editing the
body; until then this file is the authoritative correction.

## 2. `conversations.replies` immediately after `completeUploadExternal` can miss the file message

Right after stage 3 returns `ok: true` with the shared file ids, an immediate
`conversations.replies` read returned `count: 14` with **none** of the new ids, which looks like a
failed share. Retrying a few seconds later found all three ids on a NEW message authored by the
bot user (`U0AEZC7RX1Q`), with a `files` array of 3 entries and its own `ts`.

Practical rules:
- Verify against the *new bot message*, not the parent message's `files` (the parent only shows the
  requester's own uploads).
- Retry the replies read (2–3 attempts, short backoff) before declaring a share failure.
- `files.info` is the fallback identity check when the replies read still lags.
- A single `completeUploadExternal` call can share several staged ids at once; stage each file
  first (getUploadURLExternal + POST) and complete once.
