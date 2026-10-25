# Proving a full-suite failure is pre-existing (parallel-run flake)

Session evidence: `worldai_frontend`, PR #178. Local `npx jest` (310 suites, parallel workers)
failed `tests/campaignsEditModalAlert.test.tsx` while CI at the same head was green. The test
passed in isolation and in *some* full runs.

## What "dismiss as pre-existing" actually requires here
One green baseline run is **not** proof. The flake direction varies, so a single pass on
`origin/main` proves nothing. Sequence that worked:

1. Full run on the PR tree — record `Tests: N failed, M passed` and the failing test *names*.
2. Full run on a baseline worktree pinned to the exact merge-base (`origin/main` at the PR's
   rebase point) — twice.
3. Full run on the PR tree again.

Verdict rule: pre-existing is established when the **same test name** fails on baseline in at
least one run *and* the failure is non-deterministic across runs (it also passes somewhere),
with the PR diff not touching that file. Cite the exact counts from each run.

Observed pattern worth recognizing: under a shared worker pool the failing suite **moves**
(e.g. run 1 fails `campaignsEditModalAlert`, run 2 fails `navigationStatePersistence`, run 3
fails the first again). A moving failure is an ordering/leak class, not a regression from a
two-line diff — but still say so with run counts, not adjectives.

## Practical traps
- A fresh worktree has no `node_modules`. Symlinking the main clone's `node_modules` into it
  breaks jest preset resolution: `Validation Error: Preset ts-jest not found relative to
  rootDir`. Run `npm ci --prefer-offline --no-audit --no-fund` inside the worktree instead.
- Suite counts differ between trees when the PR adds a test file (310 vs 309 suites,
  3232 vs 3231 tests). Match by test *name*, not by total count.
- Report the flake in the PR comment with the baseline SHA and both run results; do not
  silently absorb it into "CI is green".

## What this does NOT excuse
Do not use this to wave away a failure in a file the PR touches, a deterministic failure,
or a failure whose assertion error differs. Those need a fix, not a dismissal note.
