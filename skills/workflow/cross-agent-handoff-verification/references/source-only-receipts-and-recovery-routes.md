# Source-only receipts and recovery-route checks

Use when a peer/operator forbids execution ("no new writer, no paid run, no mutation") but still
wants progress, or asks "who owns this lane and can it be resumed". Everything here is read-only and
produces a receipt, not an action.

## 1. The receipt form that gets accepted

One line per read: **original command · UTC timestamp · exit code · one-line result**. Peers call this
"concrete progress"; a paragraph of findings without those four fields reads as a status recap.

```bash
cd <worktree>; echo "T=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
git show --stat <sha> 2>&1 | head -20; echo "EXIT=${PIPESTATUS[0]}"
```

Two integrity rules that come up constantly:

- **A source review is not a test run.** Relaying "review posted" or your own line-number confirmation
  must say explicitly that no fixture/unit tests executed. Never let a review comment imply green tests.
- **Superseded measurements are historical, named by you.** When a peer publishes fresher host figures,
  retract your older numbers by name ("my 09:37 load/181 MB figures are historical, not the current
  blocker") instead of re-arguing them.

## 2. Read a PR head without touching a dirty worktree

A worktree with staged work must never be checked out or reset as a side effect of *reading* it.

```bash
git show <sha>:path/to/file.py            # file body at that revision
git show <sha>:path | sed -n '1,60p'      # bounded read
git grep -n 'symbol' <sha> -- dir1 dir2   # grep inside a revision, no checkout
git cat-file -e <sha> && echo PRESENT     # is the object already local?
git diff --name-only "$(git merge-base origin/main <sha>)" <sha>   # PR file classes
```

- `git grep <rev>` returning rc 1 = no match in that revision; it is not an error and not an exception.
- Classify the PR by file class before claiming what evidence it needs:
  `awk '/^mvp_site\// && !/\/tests?\// {m++} …'` gave 51 non-test `mvp_site` files → the repo's `/es` +
  captioned-video prerequisites bind, even though the head commit itself was test-only.

## 3. Symlinked policy files: `git show` returns the link text

`git show <rev>:testing_mcp/CLAUDE.md` printed exactly `AGENTS.md` — because that path is a **symlink**
in the tree. Consequences:

- A grep over it returning zero matches means **"symlink, not content"**, never "the repo declares no
  policy". Say which one it is.
- Follow the link: `git show <rev>:AGENTS.md | grep -nE 'network retr|/es|streaming|full suite'`, then
  quote the clause you are relying on at that revision.
- Repo-declared acceptance prerequisites are per-revision: read them at the PR head, not from `main`.

## 4. Identify a secret-resolution entrypoint without reading the secret

```bash
gcloud secrets list --project <p> --format='value(name)' | grep -iE 'openrouter|api-key'   # NAMES only
git grep -nIE 'openrouter-api-key|OPENROUTER_API_KEY|secrets versions access' <rev>        # declared form
[ -f ~/serviceAccountKey.json ] && stat -f '%Sp %Su' ~/serviceAccountKey.json               # presence+mode
echo "VAR: $([ -n "${OPENROUTER_API_KEY:-}" ] && echo SET || echo UNSET)"                   # presence only
```

Report the entrypoint (`gcloud secrets versions access latest --secret=<name> --project <p>`) plus
"**I did not execute it** — that reads the payload". Never print a value, never copy material between
hosts, never inspect auth stores. Presence/absence + mode + identity (`gcloud auth list
--format='value(account)'`) is the whole receipt.

## 5. Before promising a resume: capability + target + no-holder

A recovery route is real only when all three check out; say which one fails:

```bash
codex resume --help | grep -nE 'SESSION_ID|--cd'      # capability: UUID positional + -C/--cd supported
git -C <clean-worktree> log --oneline -1             # target: head == the PR head you intend
ps -eo pid,command | grep <session-uuid> | grep -v grep   # holder: empty = no competing resume
```

- A **stopped session is not an executing integrator**; resuming it is a new paid run, so it needs
  explicit authority even when the route is technically available.
- Two routes exist in practice: the incumbent lane's own session, and a clean worktree at the head.
  Prefer naming the exact invocation (`codex resume -C <clean-worktree> <uuid>`) over "resume the lane".
- If the provider backend is down, the honest line is "route requires an authorized paid run **and** a
  working backend; neither exists now" — not a manufactured receipt.

## 6. Sanitized retained-marker inventory (owner / process / checkpoint / delivery)

For a factory or cron that keeps "pending delivery"/retained-session markers, inventory the **base
markers**, not the sidecars:

```bash
ls <state>/pending-delivery/*.json | grep -v '\.chat' | grep -v '\.brief' | wc -l   # 25 of 870
```

Dump schema + booleans only (never prompt bodies): `project_id, pr_number, created_at, session_id,
native_id, workspace, request_id, brief_path, prompt, envelope` (envelope carried the instruction and a
`PR_GREEN_DELIVERY_ID`, no ack field).

Findings worth copying as a template — each dimension independently checked:

- **process/checkpoint**: every recorded `workspace` was gone on the host; every
  `~/.codex-dark-factory/sessions/<id>.jsonl` absent → no recoverable local checkpoint.
- **durable work**: `git ls-remote --heads origin` (one call, 2,065 heads) joined against each PR head
  branch → all present. One call beats 25 network round-trips.
- **delivery**: "pending marker exists" ≠ "undelivered", and the schema has **no ack field**, so
  delivery is *unknown* — state it that way.
- **smallest safe candidate** = open PR + branch on origin + no local process + smallest changed-file
  count, presented with the one read-only command that would settle the remaining ownership question.

Idle age alone is never a criterion for reclaiming a session; an absent PID alone is not proof the work
is done.
