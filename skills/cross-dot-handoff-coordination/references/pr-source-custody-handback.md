# PR source-custody handback (single-writer transfer on an existing PR)

Use when an operator asks *"who owns PR N, and is a writer actually executing?"* and then hands that
source scope to a new single writer. The artifact is a **custody record on the PR**, not a status
opinion in chat.

## 1. Idle proof (four signals, one window)

```bash
cd <repo>
gh pr view <N> -R <org/repo> --json number,state,isDraft,headRefOid,updatedAt,commits \
  --jq '{head:.headRefOid,draft:.isDraft,state,upd:.updatedAt,last:[.commits[-3:][]|{sha:.oid[0:8],date:.committedDate,head:.messageHeadline[0:70]}]}'
git ls-remote origin refs/heads/<branch>            # must equal headRefOid
git -C <branch-worktree> diff --stat origin/<branch>..HEAD   # empty => tree identical to remote
ls -lT <changed files>                              # last source write time
pgrep -f '<dispatcher-or-entrypoint>' | wc -l       # 0 => no live process
```

Report the push window as a number ("no push in ~48 h, newest source mtime 2026-10-22T20:01-07:00,
zero live processes"). Never present a single empty `ps` as proof of idleness.

## 2. Attribution

`author.login` is the shared human account for every agent lane — it identifies nobody. Read the commit
subject tag instead (`codex(gpt-6-sol):`, `[dot][OpenAI]`, `pil/<model>:`), then check the governing bead
(`br show <id>`) and the PR for `assignees` / `reviewRequests`. "No assignee, no reviewer, no ACK" is a
finding worth stating explicitly.

## 3. Ack body skeleton

```
**Custody transfer acknowledged — <writer> is sole source writer on this branch; no duplicate lane**
Recording the reciprocal side of the handback in comment <deeplink>. Nothing below was written by me.

Checkpoint at acknowledgment: head <sha> (parents <a> + <b>), draft=<bool>, <mergeable>/<status>,
diff vs merge-base <sha>: <n> files +x/−y — prod +p/−q.
Checks: <names> <state> at run <id>. Checks that passed at the previous head do not carry over.

Ownership as recorded: <writer> is the single source writer on <branch>; <verifier> is
reviewer/coordinator only — no push, no rebase, no competing branch, no second port.
Scope preserved: <bullets>. No force-push/merge/auth/provider/deploy is implied by this record.

Reciprocal boundary: <other PR/branch> stays on the <verifier> side; <writer> does not write it.
Review contract: review at the exact head on each push, re-pin before any verdict.
```

Publish it with `gh pr comment <N> --body-file <file>` after
`python3 ~/.hermes/lib/outbound_secret_gate.py check --file <file>`, then read it back
(`gh api repos/<org>/<repo>/issues/comments/<id>` → `created_at`, `chars`) so the receipt is the server's
object, not your local file.

## 4. Re-pin immediately

Observed 2026-10-25 on `jleechanorg/worldai_frontend#254`: the new owner pushed a `main` merge
(`ee96eb0a`, parents `cf115c16` + `9d9cbf4e`) and cleared draft ~2 minutes after accepting, while the ack
named `cf115c16`. Then within the same hour: `4d45b37f`, `f233f66d`, `623f0b8f` — 3 files/+157/−10 grew to
9 files/+850/−58. Consequences to state every time the head moves:

- prior green checks are historical; the new head's checks start pending;
- the "behind main" gap is closed by the merge commit, so drop that finding from the gap list;
- diff sizing must be recomputed from the new merge-base, split prod vs non-prod
  (`git diff --numstat <mb> <head> | awk …` and again with `-- 'src/**' 'app.json' 'ios/**'`).

## 5. Allowance accounting

Standing operator limit in this lane: **two complex + two short** concurrent tasks.

- Complex slots: a PR with an active source writer, and a frozen PR whose capture/verification lane is
  still running. Those two saturate the complex budget — any further source work must fit the short slots.
- An open PR with no push inside the window is **idle**, not free; do not read it as capacity.
- Count execution from receipts (push timestamp, run id, receipt file), not from `gh pr list`.
