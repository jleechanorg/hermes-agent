# Worktree / dispatch hygiene and worker-death recovery

Hard-won mechanics for dispatching coding work onto a fresh worktree and finishing the PR when the
worker does not finish it for you. Applies to any repo, any wrapper (`pil`, `claudem`, codex, AO).

## 1. Resolve the default branch by ref, never by the name `origin/main`

A clone can contain a **local branch literally named `origin/main`** (created by an old
`git branch origin/main origin/main` or a scripted fetch). It shadows the remote-tracking ref, so
`git show origin/main:src/file.ts` silently reads a stale branch and every conclusion built on it is
wrong.

- Use `refs/remotes/origin/main` everywhere: `git show refs/remotes/origin/main:<path>`,
  `git diff --stat refs/remotes/origin/main`, `git diff --numstat refs/remotes/origin/main...HEAD`,
  `git worktree add <path> --detach refs/remotes/origin/main`.
- Diagnose the shadowing directly — differing SHAs are the proof:
  `git rev-parse refs/remotes/origin/main refs/heads/origin/main`
- `git` also warns when it is ambiguous: `warning: refname 'origin/main' is ambiguous.` Treat that
  warning as a hard stop, re-read the file by full ref, and only then trust the content.
- Cheap confirmation the worktree matches real main: `git diff --stat refs/remotes/origin/main -- <files>`
  should be empty before you start editing.

## 2. Verify the worktree actually got created

Some helpers are wrapped (`git worktree add` may be shimmed, `diskm worktree-new <repo> <branch>
--base <ref> --name <name>` exists as a convenience). Never trust the helper's success line alone.

After creating a worktree, always check all three:

1. `git worktree list` shows a **new distinct directory** (not an existing one).
2. The new branch is attached to **that** directory, at the expected base SHA
   (`git rev-parse HEAD` == `git rev-parse refs/remotes/origin/main`).
3. **No pre-existing worktree changed branch.** Compare the list before and after.

Observed failure (2026-10-24, worldai_frontend): `diskm worktree-new` created the requested branch but
checked it out inside an unrelated existing worktree (`~/.worktrees/<repo>/fix-native-test-entry-...`),
moving that directory off another agent's branch and dropping that local branch. Other agents can be
live in those trees.

### Recovery when a worktree got hijacked
1. Confirm the hijacked tree is clean: `git status --porcelain` (empty = nothing to lose).
2. Restore its branch: `git checkout -b <original-branch> --track origin/<original-branch>` and verify
   `git status -sb` shows `...origin/<original-branch>`.
3. Recreate your own worktree with plain git, pointing at the branch you already have:
   `git worktree add <new-path> <your-branch>`.
4. Never delete or rebuild someone else's worktree to fix this.
5. Disclose the incident in the final report (what moved, what was restored, evidence it was clean).

## 3. A dead worker still leaves files on disk

A print-mode dispatch can exit with a transport error after writing edits, e.g. `pil -p ...` printing
`Request timed out.` A nonzero / timed-out dispatch does **not** mean "no work was done".

- First action after any abnormal worker exit: `git status --porcelain` and `git diff` inside the
  worktree. Partial edits are common; they are often complete and correct.
- **Check the tree is not still being written before you touch it.** Compare file mtimes against now
  (`ls -lt --time-style=+%H:%M:%S <new files>`, `date`), and look for a live writer with
  `lsof +D <worktree> | grep cwd` / `ps -eo pid,etime,command | grep -E "<wrapper>|node"`. Files
  modified after the worker's own exit line mean a child (or another lane) is still editing — wait or
  coordinate; a re-dispatch at that moment is a two-writer collision.
- Review the diff against the spec yourself (imports, prop threading, test coverage, no unrelated
  files). Then run the repo gates **yourself** rather than re-dispatching blindly.
- Finish the PR from that state: commit with the required provenance prefix, `git push -u origin
  <branch>`, open/refresh the PR. Re-dispatching from scratch usually duplicates work and loses the
  partial edits.
- Report honestly which parts the worker wrote and which parts you verified or repaired.

## 3a. Targeted-green is not green — run the FULL suite before pushing

Verified 2026-10-24 (worldai_frontend PR #277): the recovered worker's work passed its own six
targeted suites (172 tests) and `tsc`, so it looked ready. The repo's full suite then failed
**in a suite the change never mentions**: a streaming message's caret had moved out of the tail
text, caught only by `tests/iosResidualVisualDeltas.test.tsx`. Nothing in the targeted set touches
that file.

- Always run the CI-equivalent full command (e.g.
  `node node_modules/jest/bin/jest.js --config jest.config.cjs --rootDir . --maxWorkers=1`)
  before the first push, and again after any behavioural fix, and quote **suite + test counts**.
- Treat "targeted suites pass" as a smoke signal, never as a readiness claim; say which command
  produced which numbers.
- When the full run flags a regression you introduced, fix it in the same PR (not a follow-up),
  re-run the full suite, and re-capture any visual evidence whose code head moved.
- Bug class worth recognising on sight: a helper that returns a **wrapper object**
  (`{ narrative, block }`) with `block: null` when nothing matched, gated as
  `if (wrapper === null)` — that branch is never taken, so *every* call site silently changes
  behaviour. Gate on the inner field (`const block = wrapper?.block ?? null`), and keep one
  boundary test asserting the no-match path is byte-identical to the base head.

## 2b. Ownership pre-check before you create a branch

The scope may already have an owner — including an owner that already **merged** part of it.

```bash
git worktree list | grep -i <topic>                 # another live tree on the same scope?
gh pr list --state all --limit 30 --json number,title,headRefName,state --jq '.[] | ...'
git ls-remote origin refs/heads/main                # real main head (see §1 for stale refs)
```

- A merged PR whose title covers the same files means part of the ask is already on `main`: enumerate
  which sub-fixes landed, and scope yours to the remainder — do not re-fix shipped behaviour.
- A live worktree with recent mtimes = another writer; coordinate (who implements, who stays
  read-only) and record the answer in the thread instead of racing.


## 3b. A background worker piped through `tail` is unobservable — log to a file instead

Verified 2026-10-24 (two `pil -p "<task>"` lanes dispatched with
`bash -lic 'pil -p "…" 2>&1 | tail -60'` under `terminal(background=true)`):

- The `tail` pipe buffers everything until the worker's stdout closes, so `process(action='poll')` shows
  an empty `output_preview` for the whole run (35+ minutes of zero progress signal).
- The background session id itself can disappear mid-run (`process poll` → `No process with ID …`)
  while the worker keeps writing to its worktree. Absence of the handle is **not** absence of the work.
- Do this instead: `bash -lic 'pil -p "…" > /tmp/<task>.log 2>&1'` (no `tail`), then read progress with
  `process(action='log')` or by tailing the file from a second call.
- If the handle vanishes, recover by artifact, not by assumption: find the newest worktree
  (`ls -dt ~/.worktrees/<repo>/*/ | head`), then `git -C <wt> log --oneline -2`,
  `git -C <wt> status --porcelain`, and `gh pr list --head <branch>`. In this session both lanes had
  already committed and opened their PRs; only the handle was gone.


- `gh pr view <n> --json headRefOid` equals the SHA you just committed (not an older push).
- Required labels present (`gh pr view --json labels`), title carries the mandated suffix.
- Body carries the repo's required headings — e.g. a literal `## Evidence` heading, and the
  production-vs-non-production line deltas computed with
  `git diff --numstat refs/remotes/origin/main...HEAD` (classify by path, do not eyeball).
- `gh pr checks <n>` recorded verbatim; pending is reported as pending, never as green.
- Worktree left clean (`git status -sb` clean, upstream set).
- If another open PR touches the same file, name it in the PR body as the expected conflict surface.
