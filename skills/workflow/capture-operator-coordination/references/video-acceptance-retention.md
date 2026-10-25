# Video acceptance retention — two real PRs (2026-10-24)

Both cases: operator reaffirmed "Hermes needs before after video", named a sole iOS capture operator, and
forbade a new writer. Nothing was captured; the deliverable was *retention + pickup + exact blockers*.

## Case A — PR #131, book/emblem loading treatment

- Repo `jleechanorg/worldai_frontend`, branch `feat/campaign-opening-book-20261020`
- Candidate `bd91f39ada172606ea298c446a6475de3ba05944`, OPEN/draft
- Deltas verified here: merge-base `5204a6fc` → **PROD +18/−11, NONPROD +7/−3**, total +25/−14
  (prod = `src/` minus tests). The "split unverified" caveat in the brief was closed with one numstat run.
- Scope from the PR body: loading block only in `src/screens/GameScreen.tsx` (~3294–3316 on main);
  concept already approved ("Ok book one is fine"); spinner retained as the real activity signal;
  `progressbar`/`busy`/`polite` semantics preserved.
- Dormancy evidence: worktree `…/.worktrees/worldai_frontend/campaign-opening-book` at `5157cc75`
  (1 commit behind head), clean, **0 bound processes**; branch not checked out in any of 144 worktrees;
  Linux has only the remote ref; PR comments are CodeRabbit-only. ⇒ *dormant, not released*. Owner needs
  an explicit bounded handoff from root.

## Case B — PR #160, small bottom spinner (PendingProgressPill removal)

- Candidate `eb7f723cd8283815dbe6d479174cf647b5b772e3`, OPEN, **not draft**
- Deltas: prod **+9/−11**, nonprod **+125/−68** (total +134/−79); CI: typecheck / jest /
  hardcoded-logic-gate / ios-ci-contracts all SUCCESS; `reviewDecision` **empty** ⇒ visual + `/er` pending.
- Scope: removes `PendingProgressPill` ("Checking the rulebook…", rotating messages), keeps Act/Think/God.
- Journey to record per side, one continuous take ~20–30 s: compose an Act action → submit → pending
  state → turn completes. Expectation: BEFORE shows the pill text, AFTER does not, composer buttons stay.
- Distinct from Case A: do not merge the two evidence sets.

## Retention file template (written to `~/.hermes/state/<pr>-video-acceptance.md`)

```
# PR #<n> — required acceptance: BEFORE/AFTER video
Candidate head / branch / state / deltas (prod, nonprod, verified via numstat merge-base)
Acceptance: full matched videos; same device+account+journey; both SHAs labelled; real animation;
            reduced-motion (or explicit N/A); stills/fixtures/CI cannot substitute
Plan: baseline = origin/main at capture time; candidate = <sha>; device <UDID>; journey; captions
Blockers: account/device/capacity admission; shared-UID consumer admitted? (quote receipts);
          operator pickup msg id + state; surviving media: none/found
Not authorized: build/launch/record before admission, second operator, merge, preemption
```

## Operator pickup request (what to send)

One `cmux agent message <surface> --from hermes` containing: the PR + pinned head + verified deltas + CI
state + scope sentence + (1) ACK pickup, (2) current account/device/capacity availability, (3) which
admission receipt it needs — plus "do NOT launch, build, install, or record on this message".

Then poll `cmux agent inbox --surface <s> --state {queued,delivered,read}` and report the message id with
its state. `read` = hook consumed it; that is *pickup at inbox level*, still not an operator ACK and never
a capture receipt.

## Admission facts that gate the capture

- Shared-UID consumer admission was **not** granted: Scene receipts at `02:47:49Z`
  (`next_consumer_admitted=false`) and `02:55:24Z` ("no next admission") both say released-but-unadmitted.
- A released account/UID is not a captured window; a handed-back device is not an admitted one.
- `/tmp` media from an earlier session did not survive the reboot — recent evidence dirs must be treated
  as scratch, and durable acceptance facts belong in `~/.hermes/state`, not `/tmp`.
