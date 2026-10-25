# Capturing an ID-gated render fix — verify the record matches the classifier FIRST

Verified 2026-10-25 on `worldai_frontend` PR #277 (hide the internal creation seed-prompt row).
The candidate added a positive-ID classifier (`isCreationSeedPromptRow`, `/^seed-prompt-\d+$/`,
matching `serverId`/`id`), kept the row as an empty placeholder, and carried 23 focused tests.
Every test passed. The real-run capture then showed **no visual change at all** — the exact
trap this reference exists to prevent.

## The failure

- AFTER `0c9201f9` and BEFORE real-main `9d9cbf4e`, same origin, same session, same campaign:
  screenshots were **byte-identical** (`sha256 2c4bd536…36e7cd`), both rendering the raw
  internal setup string `Character: … | Setting: … | Description: …`.
- Cause, from the app's own campaign GET (read-only): the persisted seed entry id was
  `cFvd5AK0BuAtvGohKXQM`; three other campaigns started with `turn_rid_*`. **Zero** `seed-prompt-*`
  ids existed on the account. The classifier could never fire, so the fix was inert for every
  record available to capture.

## Pre-capture gate (5 minutes, read-only, no mint)

1. Read the classifier predicate and the exact field it tests
   (`grep -n "SEED_PROMPT_ID\|isCreationSeedPromptRow" src/utils/*.ts src/components/*.tsx`).
2. Read how history entries become client messages — the field must actually be populated on the
   reload path (`grep -n "serverId" src/services/mvpSiteClient.ts`); a live-stream-only field makes
   the fix work in-session and fail on reopen.
3. Open the target record in the real app and capture the API payload the app itself fetches
   (`page.on("response", …)` on `/api/campaigns/<id>`), then list entry ids for the first N entries.
4. Assert at least one record satisfies the predicate. **If none do, stop and report**: the run
   cannot evidence the fix, and a "before/after" pair would be two identical screenshots.
   Say `fix inert for this data` — not `evidence missing`.
5. Sample ≥3 records before generalising; a single non-matching record can be a legacy path.

## Assertion shape (phase-specific, defect-shaped)

Never reuse the candidate's assertion on the baseline. Each phase expects the *opposite* defect
signature, and the receipt records `expected`/`observed` per assertion plus `assertions_passed`:

| phase | expectation |
|---|---|
| after | target node present **and empty**; leaked text absent |
| before (true main) | no testID exists at all — assert the **raw persisted text/mode is visible** in the existing row |
| before (controlled composition) | only the substitution label that composition injects |

Verified real-main behaviour: `9d9cbf4e` has no `message-creation-seed-row` testID, no label
literal and no classifier — asserting either on that head guarantees a false FAIL. Bind each
expectation to the actual retained record (the persisted text), never to the candidate's markup.

## Legacy-reference parity is a separate, cheap check

When the change claims parity with an older UI, compare DOM rects against a capture of that
reference: matching to sub-pixel (card `y` 248.875 vs 248.90625, wordmark 151.015625×41.796875
identical) proves geometry parity deterministically, and exposes pre-existing clipping that the
change did not introduce (landscape card bottom 443.2 > 375 viewport in both reference and candidate).

## Firebase SDK fixture session for the capture origin

Used when the reviewer approves SDK fixture auth but forbids UI-login screenshots.

- **Origin-scoped**: Firebase web sessions are per origin (`localhost:19026` ≠ `localhost:19031`).
  Plan ONE origin and swap the served build behind it, rather than one sign-in per port.
- **Default app only**: exchanging the custom token through a *named* app
  (`firebase.initializeApp(cfg, 'pr277-capture')`) persists the user under a different key, so the
  product app never sees the session (observed: `signInWithCustomToken` returned a real uid, reload
  still showed the signed-out landing). Call `firebase.initializeApp(cfg)` / `firebase.app()` so the
  session lands in the key the product reads. Then reload once.
- Load the SDK in-page from gstatic (`firebase-app-compat` + `firebase-auth-compat`), exchange with
  `signInWithCustomToken`, and derive identity from `auth.currentUser`.
- **Never log the token**: keep it in a single in-memory variable, `del` it after exchange, and keep
  a ledger of `{mints, at_utc, uid, token_logged:false}` instead.
- Resolve the UID from the account email read-only (`firebase_admin.auth.get_user_by_email`) — do not
  trust an env `*_TEST_UID` var; in this session it pointed at a different identity.
- Prove bypass-off with data, not flags: instrument requests and record
  `all_have_bearer: true`, `any_bypass_header: false` for every `/api/` call.
- Check `provider_data`: an account with only `google.com` has **no password provider**, so an
  email/password SDK login cannot work without linking a credential (a grant change).

## Receipt fields that made the finding reviewable

`phase, origin, build, campaign, seed_row_nodes, raw_internal_setup_visible, screenshot_sha256,
video sha256/bytes, assertion table, auth_method, disclosure` — plus the campaign API snippet that
shows the persisted ids. The identical before/after hash is the strongest single line.
