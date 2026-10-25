# Running a JS/RN PR head's suites without touching the repo tree

Verified 2026-10-23 on `jleechanorg/worldai_frontend` PR #240, head
`22430a759d06796ed865065e39a368a9e5cea948` (a Slack "re-review at this head" ask).

## Why not a worktree

`git worktree add --detach ~/.worktrees/worldai_frontend/pr240-rev-22430a7 <sha>` is the *legal*
form under this workspace's worktree guard, but it was still running at **322 s** and had to be
killed — the checkout is the slow part on a large Expo/RN repo with big binary assets. `git archive`
produces the same file tree in a couple of seconds and leaves no worktree refs or teardown debt.

## Recipe

```bash
REPO=~/project_worldai_frontend/worldai_frontend
HEAD=22430a759d06796ed865065e39a368a9e5cea948
PARENT=47c66006218a9119b79ff48147cd8ea05d886b85   # previous head / pre-fix commit

# 1. Materialise both trees outside the repo
mkdir -p /tmp/pr240repo-head /tmp/pr240repo-parent
git -C "$REPO" archive "$HEAD"   | tar -x -C /tmp/pr240repo-head
git -C "$REPO" archive "$PARENT" | tar -x -C /tmp/pr240repo-parent

# 2. Borrow dependencies (the primary clone often has node_modules but no jest)
ls -d ~/.worktrees/worldai_frontend/*/node_modules/.bin/jest | head -5
ln -sfn ~/.worktrees/worldai_frontend/<some-worktree>/node_modules /tmp/pr240repo-head/node_modules
ln -sfn ~/.worktrees/worldai_frontend/<some-worktree>/node_modules /tmp/pr240repo-parent/node_modules

# 3. GREEN at head — call the binary, never `npx jest`
cd /tmp/pr240repo-head && ./node_modules/.bin/jest --ci \
  tests/campaignOpenPayloadBudget.test.ts \
  tests/gameScreenOlderHistoryPaging.test.tsx \
  tests/iosCampaignOpenBoundedFetch.test.ts \
  tests/prependHistoryPagination.test.ts

# 4. RED at parent — carry ONLY the new/changed test file onto the pre-fix tree
cp /tmp/pr240repo-head/tests/iosCampaignOpenBoundedFetch.test.ts \
   /tmp/pr240repo-parent/tests/iosCampaignOpenBoundedFetch.test.ts
cd /tmp/pr240repo-parent && ./node_modules/.bin/jest --ci tests/iosCampaignOpenBoundedFetch.test.ts
```

## Results from that session (shape to imitate when reporting)

- GREEN at head: 4 suites → `Tests: 17 passed` (one suite failed to **run**: `Cannot find module
  'expo-secure-store'` from the borrowed `node_modules` → env-blocked, "never ran", hosted CI covers it).
- RED at parent with the head's test file copied in: `Tests: 1 failed, 9 passed, 10 total`, failing on
  exactly the new assertion — `Expected value: not "history-0" / Received array: ["history-0","history-1"]`.
  That is the semantic flip: fallback ids collided with the loaded window's ids and the prepend dropped
  the page.

## Pitfalls

- `npx jest` re-resolves the package and tries to install it:
  `npm warn exec The following package was not found and will be installed: jest@30.5.2` then
  `● Validation Error: Preset ts-jest not found relative to rootDir /private/tmp/...`. Always
  `./node_modules/.bin/jest`.
- A `node_modules` with no `.bin/jest` means deps were never installed in that clone — find one that has
  them (`ls -d ~/.worktrees/<repo>/*/node_modules/.bin/jest`).
- Borrowed `node_modules` is a different install than the head's lockfile; native packages may not
  resolve (`expo-secure-store`, etc.). Report those suites as **env-blocked / never ran** and cite the
  hosted `mobile-jest` (or equivalent) run at the head as the covering receipt.
- Teardown: `rm -rf /tmp/pr240repo-{head,parent}` when done; kill a stuck `git worktree add` PID and
  confirm (`ls -d ~/.worktrees/<repo>/<name>-rev-*`) that no half-created worktree was left behind.
