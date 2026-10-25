# Node/Jest exact-head validation in a worktree with no `node_modules`

Verified 2026-10-24 on `worldai_frontend` PR 188 @ `5b4e6649` (Jest 29.7.0 / ts-jest 29.4.15,
44/44 pass, exit 0; both `tsc` runs exit 0).

## 1. Create the checkout, then borrow the toolchain

```bash
git worktree add --detach ~/.worktrees/<repo>/prN-exact <sha>
cd ~/.worktrees/<repo>/prN-exact && git rev-parse HEAD      # pin the receipt head
ln -sfn ~/.worktrees/<repo>/<sibling-with-deps>/node_modules node_modules
CI=1 node node_modules/jest/bin/jest.js -c jest.config.cjs \
  --runInBand --runTestsByPath tests/<a>.test.tsx tests/<b>.test.ts
echo "JEST_EXIT=$?"
```

- Symlink the **whole** `node_modules` from a sibling worktree of the same repo that has deps
  installed. Do not `npm ci` in the throwaway tree; do not write into the sibling.
- Invoke `node node_modules/jest/bin/jest.js` directly. Bare `npx jest` can resolve a different
  (global/other) Jest and silently change the version in your receipt.
- Keep the repo's own `jest.config.cjs` (`rootDir` = the worktree). It works once `node_modules`
  resolves through the symlink.
- Typecheck separately and capture both exit codes:
  `node_modules/.bin/tsc --noEmit` and `node_modules/.bin/tsc -p tsconfig.jest.json --noEmit`.
- Persist the log to a timestamped path and hash it: `shasum -a 256 /tmp/<name>-$(date +%Y%m%dT%H%M%S).log`.

## 2. Dead ends (do not repeat)

Jest resolves `preset` and `transform` module names **relative to `rootDir`**, so a hand-written
temp config pointing at absolute paths fails with, in order:

- `Preset ts-jest not found relative to rootDir …`
- `Module /abs/path/node_modules/ts-jest in the transform option was not found.`
- with `rootDir` switched to a dependency-bearing tree: `Module ts-jest in the transform option was not found.`
- and with `modulePaths` + inline tsconfig, `ts-jest` typechecking fails on
  `Cannot find module 'react-native'` / `Cannot find name 'expect'` because `@types` resolve from
  the requiring file's tree.

The single working move is the symlink above. Note also that a bare `node_modules` symlink pointing
at a clone whose `node_modules` is **empty** produces the same "Preset not found" error — check the
target actually contains `ts-jest` before debugging config.

## 3. Bind the receipt to the claimed blobs

```bash
git rev-parse <remote-branch>:src/screens/X.tsx   # compare to the PR body's source blob
git rev-parse <remote-branch>:tests/X.test.tsx    # compare to the test blob
```

If both match, owner-reported results become *reproduced* results at that head — say so explicitly
and still label which numbers came from your own run vs the owner.

## 4. Conflict probe on the same head

```bash
git merge-tree --write-tree --name-only refs/remotes/origin/main <head>
```

Use the **fully qualified** `refs/remotes/origin/main`. A stray local branch literally named
`origin/main` makes the short name ambiguous (`warning: refname 'origin/main' is ambiguous`) and
silently hands you the wrong tip. Report the conflict file set (e.g. "tests only, source
auto-merges") because it decides whether new visual evidence survives the rebase.

## 5. Prove a *missing assertion* instead of just describing it

When the gap is "no test covers this state", execute it rather than reasoning from source:

```bash
cp tests/X.test.tsx /tmp/X.test.pristine.tsx
# append a temporary it('PROBE …') that console.logs the rendered text list, then asserts the invariant
CI=1 node node_modules/jest/bin/jest.js -c jest.config.cjs --runInBand \
  --runTestsByPath tests/X.test.tsx -t 'PROBE <name>'      # expect 1 failed, capture the console.log
cp /tmp/X.test.pristine.tsx tests/X.test.tsx
git status --porcelain                                     # only intended untracked files remain
```

Appending to the existing test file reuses its render/mock helpers; a separate probe file would
have to re-declare ~100 lines of mocks. Always restore from the pristine copy and show the clean
`git status` in the receipt — an unmethodical revert looks like a source edit to another owner.

## 6. Retained-owner reconciliation before touching a shared PR

Queue beads (`dotq-*`) live in the roadmap queue store, **not** the repo's `.beads`:

```bash
cd ~/roadmap/operations/jlc-mini-queue && br show dotq-<id>
cat capacity.json      # limits + current_admitted; empty lists do not prove vacancy
```

Read the `queue_record` + `retained_owner` fields and the linked WIP checkpoint
(`jleechanorg/roadmap` → `docs/wip-checkpoint-<date>.md`) before any edit. A read-only validation
run is not a claimed admission slot; say that explicitly when reporting.
