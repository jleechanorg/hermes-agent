# Successor supersession and shared-capacity admission

Session detail behind the SKILL.md section "Becoming the successor: close superseded work, but prove
the release". Verified 2026-10-24 on `jleechanorg/worldai_frontend` PR #195 → PR #278 (bead
`dotq-7dsw`, superseded bead `dotq-b442144a9a8c`).

## 1. The instruction shape that triggers this

> "First reconcile existing TopBar/CampaignsScreen owner `dotq-b442144a9a8c` / PR195; don't create a
> competing writer or conflate GameScreen PR58. Respect shared two-complex/two-short admission.
> Return pickup plus actual branch/head/first safe action receipt."

Two things are being asked at once: **one source writer** and **a receipt, not an acknowledgement**.
Handle the ownership question first; source edits before it are the defect.

## 2. Evidence ladder for "the incumbent has no live writer"

Run all five, quote all five. Any single one is circumstantial.

```bash
gh pr view <n> --json number,state,isDraft,headRefName,headRefOid,updatedAt,mergeable,mergeStateStatus,files
git -C <incumbent-worktree> log -1 --format='%ci %H %s'
gh pr view <n> --json comments --jq '.comments[] | "\(.createdAt) \(.author.login)"'   # last human touch
git fetch -q origin main
git merge-tree --write-tree --name-only <pr-head> refs/remotes/origin/main   # then read the file list
ps aux | grep -iE '<branch|worktree key>' | grep -v grep                      # no writer process
stat -f '%Sm %N' <worktree>/src/<changed file>                                # mtimes match last commit
```

Session result: head `36d87c73`, draft, base `93a1e74d` while real main was `f7768675`,
`mergeable=CONFLICTING`, last commit 2026-10-21 14:36 PDT, last comment 21:36Z, conflicts confined to
`src/screens/CampaignsScreen.tsx` + `tests/topBarBackButton.test.tsx` (TopBar auto-merged), worktree
mtimes on 2026-10-21, no process. Verdict: no active owner → supersession is legitimate.

## 3. Supersession sequence (reversible)

1. Write the reconciliation receipt to a file, run the outbound secret gate, post it as a comment:
   ```bash
   python3 ~/.hermes/lib/outbound_secret_gate.py check --file /tmp/reconcile.md
   gh pr comment <n> --body-file /tmp/reconcile.md
   gh pr close <n>
   gh pr view <n> --json number,state,closedAt,headRefOid
   ```
2. In the receipt state: inspected head, why the design is superseded, **what is salvaged and
   re-applied in the successor** (e.g. pill truncation, shrinkable flex group, duplicate-gear removal)
   and **what is dropped** (e.g. its labelled top-level theme control).
3. Preserve the branch and worktree. `closedAt` + unchanged `headRefOid` is the proof nothing was
   rewritten; say "reopening is a one-click decision".
4. Cut the successor from `refs/remotes/origin/main` (qualified — see the ref-shadowing trap below)
   and record: branch, worktree path, head SHA, `git ls-remote --heads origin <branch>` (0 refs =
   local only), `git status --porcelain` (clean or the exact untracked test file).

## 4. The pushback you should pre-empt

A peer rejected the first receipt with two correct objections, both worth copying into future receipts:

- *"Closing it does not establish that the incumbent released the source... it asserts successor scope
  but supplies no named executing operator."* → Name the operator and the decision authority.
- *"The comment labels inspection 18:30Z, later than its creation, so that timestamp needs correction
  rather than being treated as execution proof."* → Do not hand-write a clock. Local `date +%FT%T%z`
  is valid for *commands you ran*; artifact times come from the platform (`created_at`,
  `closedAt`, `git reflog --date=iso`). Publish a correction naming the withdrawn figure.

Working shape of the corrected receipt:

```
Who decided: <agent/session/identity>, on user instruction "<quote>"
Branch/worktree/head: <branch> @ <sha>, created <reflog time> from refs/remotes/origin/main,
  worktree <abs path>, pushed refs: none
Source edits so far: none / <exact list>
First executed command (original local time <ts>): <cmd> → <one-line result>
Running writer process: none (checked <command>)
Occupancy: admission.py status → {...}; capacity.json → {...}; check <task_key> → refused, reason ...
```

## 5. Capacity admission semantics (`operations/jlc-mini-queue`)

`admission.py` reads `queue-index.json` entries and the `br` database, under `.queue.lock`:

- `status` → `{"limits":{"complex":2,"short":2},"active":[...],"all_records":N}` — `active` lists only
  `in_progress` beads, i.e. the authoritative occupancy count.
- `check <task_key>` → `{"allowed": false, "reason": "unknown task"}` when the bead has no
  `queue-index.json` entry. This is a **registration gap**: capacity may be completely free
  (`active: []`, `active_complex: []`, `active_short: []`) and the guard still refuses, because it
  cannot resolve the task to a bead.
- `admit <task_key> --owner-receipt '<reconciliation>'` requires that entry and an owner receipt;
  it writes `status=in_progress` with `--if-unchanged` on the bead's `updated_at`, appends a receipt to
  `receipts/admissions.jsonl`, and records that admission is not execution proof.
- The store's own slot rules reserve mutation to the **designated queue writer**. A driving agent
  reports the gap and requests the index write; it does not edit `queue-index.json` or the bead file.

Report shape that peers accept: store counts (free slots), the exact refusal string, and the single
requested action for the queue owner.

## 6. Ref and environment traps hit during this session

- **A local branch named `origin/main` shadows `refs/remotes/origin/main`.** `git for-each-ref` showed
  both; unqualified `origin/main` printed `warning: refname 'origin/main' is ambiguous` and
  `git rev-list --left-right --count origin/main...HEAD` returned `0 3` (against the *stale* branch)
  while the real remote main carried ~5 days of commits including files the PR touches. Always qualify
  and cross-check `gh api repos/<o>/<r>/commits/main --jq .sha`.
- **`gh pr view --json files` is the overlap check**, not the PR title: PRs `#276`/`#253` also touched
  campaigns surfaces and had to be separated from the TopBar/CampaignsScreen scope by path.
- **Heredoc commit messages containing `&` trip the shell guard.** Write the message with the file
  tool and `git commit -F <path>` instead of a heredoc.

## 7. What not to claim

Supersession proves ownership, not delivery. Keep these separate in the same message: reconciliation
receipt (done), source head + tests (measured), CI (pending/absent), visual evidence (not captured),
readiness gates (`/es`, `/er`, `/cs` unmet). A draft PR with honest pending sections is the correct
artifact — not a "ready" claim with a mock or fixture standing in for runtime proof.
