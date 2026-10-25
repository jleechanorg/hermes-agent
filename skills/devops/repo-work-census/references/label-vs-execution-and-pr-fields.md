# Label vs execution, and PR-field traps (session receipts, 2026-10-24)

## 1. The five-lane reclassification

Claimed at `02:54:47Z` from `esc to interrupt` text: "5 lanes executing". Re-measured `03:10:25Z`
with a fresh-mtime sweep + pane bodies:

| Lane (surface UUID) | cwd / head | Actual attributable action | Fresh file in 60 min | Class |
|---|---|---|---|---|
| dropbox `0AC677C1…` | `worktree_dropbox` `38ed1a1` (moved from `ebc5b6e`) | `rtk ls -la`, disk-delta table, then "Requesting current status (3h 19m 41s)" | only `.pytest_cache/…/nodeids` | real read, no task artifact |
| zoom `A54137EF…` | `worktree_p0_2423423` `48f5279` | `idb ui describe-all --help`, `top -l 2`, `cmux agent inbox --mark-read` → "Compacting context (1m 25s)" | none | label-only |
| creation UI `8C616824…` | `worktree_ios_creation_flow` `b20836dd` | `ssh jeff-ubuntu … scroll9733-refresh-main-20261024 && git rev-parse HEAD` → `696641ef` | none locally | real read (cross-host) |
| outcome UI `208A07C8…` | `worktree_outcome_ui` `e53106d0` | `ssh … top`, `rtk grep` skills → "Compacting context (11s)" | none | label-only |
| auto-creation `EBB662EB…` | `worktree_autocrrstion` `74c6c426` (1608 dirty, mid-merge) | sent `cmux agent message … --from opening-10577` "Opening acceptance status 03:12UTC: PR #10577 at 415aa459" | none | genuinely active — message only |

Operative rule: the mtime sweep is the discriminator. "Zero files modified in any of the five cwds in
the last 60 minutes" is what makes the label claim false; the pane text alone cannot.

Also in that lane: 1608 dirty entries resolved to an **interrupted merge**, not authored work —
`MERGE_HEAD` = `af69f44b` ("fix(schema): align character edit OpenAI contract [codex][gpt-6.1-sol]"),
**104 conflicted paths** (92 `UU`, 7 `UD`, 5 `AA`), composition `mvp_site 875 / testing_mcp 306 /
docs 244`. Symptom → cause chain:

```bash
G=$(git -C "$D" rev-parse --git-dir); for f in MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD; do [ -e "$G/$f" ] && echo "PRESENT: $f"; done
git -C "$D" diff --name-only --diff-filter=U | wc -l
```

Never report a conflict index as "N ready edits" — it belongs to the incoming branch's content.

## 2. PR fields — the three mis-reads

| Mis-read | Truth |
|---|---|
| `updatedAt 17:47:06Z` treated as a push | comment at `17:47:05Z`, 1506 B; last commit `03:18:46Z` |
| `updatedAt 01:24:41Z` quoted as merge time | `mergedAt 01:19:59Z`; `updatedAt` trails by the merge-commenting |
| `e0cef741` called "the superseded candidate" | it is `mergeCommit.oid` (post-merge main); `headRefOid` was `22430a75` |

```bash
gh pr view <N> -R <o>/<r> --json headRefOid,mergeCommit,mergedAt,updatedAt,additions,deletions,statusCheckRollup
gh pr view <N> -R <o>/<r> --json comments -q '.comments[-3:][]|"\(.createdAt) \(.author.login) \(.body[0:60])"'
```

## 3. `origin/main` ambiguity

A local branch literally named `origin/main` makes ancestor tests unreliable:

```
git merge-base --is-ancestor bfc5c429… origin/main
warning: refname 'origin/main' is ambiguous.
NOT_ON_MAIN          # wrong — the commit came from a MERGED PR into main
```

Use `refs/remotes/origin/main`, or `gh pr view --json mergedAt`, and state the instrument in the reply.

## 4. Panel/title binding traps seen this session

- `cmux list-panels` lists **only the current workspace** (2 panels while ~59 surfaces existed).
- `surface:` numbers rotate after a Mac reboot and after panes close: bind **UUID + cwd**, then re-derive
  head with `git -C <cwd> rev-parse HEAD`.
- A workspace titled `ui cutover` hosted a live session on an **unrelated branch** — the label was the
  trap; the cwd/HEAD was the answer.
- `cmux tree --all` output is the only place that carries `surface surface:<n> <UUID> "title" tty=…`.

## 5. `cmux agent inbox` mechanics worth knowing

```bash
cmux agent inbox --state queued|delivered|read|failed      # `--state all` is rejected
cmux agent inbox --surface surface:<n> --state read        # per-surface lookup
cmux agent inbox --json                                    # records: id, body, created_at, read_at,
                                                           # delivered_at, state, sender_name, recipient_*
```

- The message text field is **`body`** (not `text`); a `.get('text')` parse silently prints blanks.
- **Without `--surface` the listing covers every surface**, so you see `scene-root → <other surface>`
  rows that are *not* addressed to you — do not quote them as replies to your request.
- An **idle** lane never drains its inbox: its row stays `queued` indefinitely, which is not refusal.
  A lane at `read` consumed the row via hooks; that is still not an ACK.
- `cmux vault sessions --limit N` can exceed a 45 s budget; `cmux recover` depends on `sr` being present.
  If either is unavailable, say the route gap rather than substituting a filesystem grep for the relay id
  (recursive greps over cmux/codex/claude state do not finish inside 180 s).
