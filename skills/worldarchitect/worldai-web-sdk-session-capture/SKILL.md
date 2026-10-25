---
name: worldai-web-sdk-session-capture
description: Signed-in worldai_frontend web capture, no human login.
version: 1.0.0
author: hermes
license: MIT
metadata:
  hermes:
    tags: [worldai, playwright, firebase, evidence, capture]
    related_skills: [wa-visual-proof-playwright, browser-headless-default]
---

# worldai_frontend: authenticated web capture without human login

## When to Use
Use when a PR needs real signed-in before/after evidence at a local Expo web origin, when a manual
Google login is the only blocker, or when `testing_mcp.run_contract` must run without a human sign-in.

## Hard constraints (learned, non-negotiable)
- **Token never leaves memory**: no argv, no console, no HAR, no receipts, no gist. Report mint count only.
- **No copied/injected app state**: create the session with a real SDK sign-in, never storageState/token injection.
- **One operator per capture lane**; never attach a debugging endpoint to someone else's live Chrome.
- **Firebase auth is origin-scoped** (`scheme://host:port`). `:19026`, `:19031`, `:19033` are different sessions.
  Reuse ONE origin for both phases (swap the served build behind the same port) instead of minting per phase.
- Metro **dev** bundles are rebuilt per server start: a checkout SHA does not identify the bytes the browser
  loaded. Hash the `index.bundle` response **in the capture session** (`page.on("response")` → sha256 of `r.body()`);
  a later curl of the same URL gives a different hash and is not evidence.

## Session bootstrap (no human, no manual login)
1. `git worktree add --detach <diskm-approved path> <candidate-sha>`; `npm ci --prefer-offline`.
2. Serve: `EXPO_NO_DOTENV=1 EXPO_PUBLIC_BACKEND_URL=<dev cloud run> CI=1 node node_modules/expo/bin/cli start --web --port <port>`.
3. Playwright `launch_persistent_context` on the task-owned profile
   (`/home/jleechan/.config/dot-headless-chrome-test`, `--profile-directory=Profile 2`, headless).
4. Load `firebase-app-compat.js` + `firebase-auth-compat.js` from gstatic **into the page**, then
   `firebase.initializeApp(cfg)` with **no custom app name** — a named app persists under a different key and the
   product's `[DEFAULT]` instance will not see the session (this exact mistake wastes a token).
5. Only when a custom token is explicitly approved: `firebase_admin.auth.get_user_by_email(email)` → mint token →
   `page.evaluate` `signInWithCustomToken(token)` → wait for `onAuthStateChanged` → reload → product shows the dashboard.
   For read-only reuse, just `firebase.auth().currentUser.getIdToken()` on the restored session (no mint).

## Capture
- Split phases: one run per build, same origin, same profile. Swap server, reload, capture — session survives.
- Record per phase: build sha, campaign id, screenshot sha256, video sha256, `index.bundle` in-session sha256+bytes,
  UTC timestamp, and a `disclosure` string naming the auth method ("SDK fixture authentication", not "UI Google login").
- Ship videos to Slack with `files.getUploadURLExternal` → raw POST → `completeUploadExternal` using
  `channel_id` + `thread_ts` and **no `initial_comment`** (a comment silently drops mp4/webm/doc attachments).

## Pitfalls that invalidate evidence
- `seed-row` assertions must be **phase-specific**: AFTER = row present + text empty; BEFORE = the original defect
  visible (raw `Character: … | Setting: …`, or the literal label on a composition build). Never apply one side's rule to both.
- The client's seed-row classifier matches only `^seed-prompt-\d+$`; many persisted rows carry random or `turn_rid_*`
  ids, so the fix can be inert. Prove the specimen's persisted id before claiming a delta.
- History pagination: the first returned window can be a newest-boundary window. `has_older` + `before_id` paging is
  required to reach campaign start; the transcript is an **inverted FlatList** and may not load older rows from a
  plain wheel-at-top — use the app's own load-older trigger, not blind scrolling.

## testing_mcp.run_contract (read-only)
Required env or it exits 2 with "BLOCKED: invalid or missing runtime prerequisites":
`TESTING_AUTH_BYPASS=false`, `ALLOW_TEST_AUTH_BYPASS=false`, `WORLDAI_TEST_ACCOUNT_KIND=dedicated`,
`WORLDAI_BACKEND_TIER=dev|local`, `WORLDAI_BACKEND_URL`, `WORLDAI_FRONTEND_URL`,
`WORLDAI_FRONTEND_SHA` + `WORLDAI_BACKEND_SHA` (**40-hex git shas**, not image digests; backend sha from image tag),
`WORLDAI_EVIDENCE_ROOT` (must resolve under `/tmp`), `WORLDAI_FIREBASE_ID_TOKEN`.
Record harness HEAD separately from the app HEAD. Report the report's provenance flags honestly — they are all
`false` by design (`served_identity_verified`, `backend_bypass_verified`, `account_identity_verified`).

## Verification receipts that actually hold up
`git merge-base` / `numstat` for deltas, `sha256sum` of served bundle in-session, `ffprobe` for clip geometry,
Cloud Run `revisions describe` env dump (beware: dev defines `SMOKE_TOKEN`, header-gated, unused by clean requests),
and an API response that echoes the account uid for identity binding.
