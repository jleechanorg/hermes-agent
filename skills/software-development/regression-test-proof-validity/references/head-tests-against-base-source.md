# Discriminating RED for a JS/jest fix: run the HEAD's tests against the BASE source

Verified 2026-10-24 on `worldai_frontend` PR #257 (`ZoomableImageViewer` pan-end fix, head `f32dbf5e`,
pre-fix head `0d0f2335`). Produces a RED/GREEN pair in minutes when pixels cannot discriminate
(see `rnw-visual-evidence/references/gesture-ordering-route-limit.md` for that case).

## 0. Pin the TRUE head first (this caught a self-inflicted error)

A commit quoted in a status doc or an earlier receipt is not the head. Before any head claim:

```bash
gh pr view <n> --repo <owner>/<repo> --json headRefOid,baseRefOid,state -q '.headRefOid'
git rev-parse HEAD                                    # in the worktree you think is the head
git merge-base --is-ancestor <older-sha> <head-sha>    # ancestry, not commit-list position
```

A worktree checked out at an *intermediate* PR commit still holds a coherent, self-consistent version
of the code — in this session an intermediate head made the fix look **reverted** (`finish('pan')`
absent, regression test deleted), when the real head `f32dbf5e` contained both. `gh --json commits`
lists commits oldest→newest, so slicing the tail tells you nothing about which one is the head.

## 1. Replay shape

```bash
# BASE worktree at the pre-fix head (source under test)
cd ~/.worktrees/<repo>/<base-wt>              # HEAD = 0d0f2335
cp tests/<suite>.test.tsx /tmp/base-suite.orig.tsx          # keep the original bytes
cp ../<cand-wt>/tests/<suite>.test.tsx tests/<suite>.test.tsx   # HEAD's test file, BASE's src
npx jest tests/<suite>.test.tsx 2>&1 | tail -25
git checkout -- tests/<suite>.test.tsx        # restore; prove with git status --porcelain
```

- Expect failures whose **message names the symptom**, not a compile error. Passing evidence:
  `Expected: ArrayContaining [1, 0]` / `Received: [0]` — the scale never snapped back.
- A suite that is red for setup reasons (cannot resolve module, TypeScript error) is **not** RED;
  retract it. (See `references/seam-driven-behavioral-red.md`.)
- Same command in the candidate worktree must be green at the head: `30 passed, 30 total`.
- Quote both counts and the exact assertion line; "the test passes now" is not a receipt.

## 2. Worktree mechanics

- `git -C <existing-wt> worktree add -f --detach <path> <sha>` is enough; a relative `<path>` resolves
  against the **main** worktree, so re-read `git worktree list | grep <sha>` instead of trusting `ls`.
- `ln -sfn <other-wt>/node_modules <new-wt>/node_modules` is sufficient for **jest**.
- It is **not** sufficient for `expo start`/Metro: bundling fails with
  `Unable to resolve "react-native-gesture-handler" from "index.js"`. Do not conclude the app is
  broken — a real install (or a static `expo export`) is needed for the serve lane.
- Remove the throwaway worktree afterwards (`git worktree remove --force <path>`) so the census stays
  honest.

## 3. What this does and does not prove

Proves: the new tests discriminate the repair at the exact head; the base source fails them.
Does not prove: rendered behaviour, app-shell acceptance, or native gesture semantics. Label it
"regression proof" and keep visual/native claims separate.
