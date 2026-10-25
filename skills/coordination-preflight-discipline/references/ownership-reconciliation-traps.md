# Ownership & occupancy reconciliation — instrument traps and receipt recipes

Field notes from a multi-endpoint (Mac / Linux / cloud-bot) PR ownership reconciliation run.
Every item below is a case where the first reading was WRONG and the corrected instrument
produced the answer. Use these before asserting "no owner", "not executing", or "vacant".

## 1. Absence is an artifact until the window is exhausted

- `conversations_replies(limit=40)` returns a **page plus a cursor**. Concluding "zero replies
  from endpoint X" from that page is a pagination artifact. In the run that produced this note,
  a peer bot's authenticated reply was present in the thread and missed this way — the
  correction came from the owner, not from my own re-read.
- Any "no reply / no ACK exists" claim must state the range scanned and whether a cursor was
  left unconsumed. Otherwise report `UNKNOWN — window truncated`, never `ABSENT`.
- Thread replies are invisible to `conversations_history` (channel-top only). A message that
  "does not exist" in channel history may be a thread reply; fetch it by `thread_ts`.
- There is no single-message fetch equivalent to `conversations.info` in the default Slack MCP
  toolset. A linked `.../p<ts>` that has no thread returns `thread_not_found`, and a
  channel-top message cannot be fetched by ts at all. Name that as the capability gap; do not
  claim the message is missing or refuse the task on it.

## 2. Delivery ≠ pickup ≠ execution (three separate states)

| State | What proves it | What it does NOT prove |
|---|---|---|
| delivered / queued | relay id, inbox row `queued`/`delivered` | anyone read it |
| read | inbox row state `read` | pickup, agreement, or any run |
| pickup | owner-authored ACK naming the task | execution |
| execution | command + artifact + timestamp from the owner's own session | acceptance |

Never collapse these. A `read` inbox row is the single most common false "owner confirmed".

## 3. Observer read keeps its own class label

An aggregate surface report ("surface:N is actively working on PR X") is an **observer** read,
even when it appears in the same channel as owner messages. It is not an owner ACK, not a
handback, and not execution proof. Say `observer` explicitly when quoting it.

## 4. Stalled, released, and vacant are different

- `Goal stalled (/goal resume)` in an agent pane = **stalled**. A stalled lane still holds its
  reservation; it is not released and its slot is not free.
- No bound process + local head == remote head + untouched tree + no newer artifacts =
  `inactive-by-silence` (weaker than a release). Do not upgrade it to "released" or "vacant".
- A missing incumbent-authored handback is not by itself a release gate once the user
  explicitly authorizes recovery; but it also never converts silence into vacancy.

## 5. Attribution: commit tags and authorship are not actors

- `[codex][gpt-6-sol]` in a commit subject and `jleechan2015` as author are **attribution
  strings on a shared machine identity**. They identify the tool path, not a live operator.
- A local branch named `audit/...` proves a ref existed, not who created it.
- A live actor requires: process → cwd → branch/head, or an owner-authored message mentioning
  the task. If neither exists, the honest verdict is `UNRESOLVED_OWNER`, which is not vacancy.

## 6. Pin "the preserved original" per host

The same branch name can point at different commits on different machines (e.g. Mac worktree
at `c7e1f6ac` with 3 dirty files vs Linux worktree at `01449563` clean). A receipt that says
"original preserved" without host + commit + dirty list is not actionable.

## 7. Recoverable-patch receipt (preserve dirty work without touching it)

```bash
F=<path/relative/to/repo>
OUT=/tmp/<area>/preserve-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT"
git diff --binary -- "$F" > "$OUT/name.patch"
shasum -a 256 "$F" "$OUT/name.patch"; wc -c "$F" "$OUT/name.patch"
git apply --check --reverse "$OUT/name.patch"   # patch ≡ current dirty content
T=$(mktemp -d /tmp/check.XXXXXX); mkdir -p "$T/$(dirname "$F")"
git show HEAD:"$F" > "$T/$F"
( cd "$T" && git apply --check "$OUT/name.patch" )  # patch reapplies from pristine head
git status --porcelain; shasum -a 256 "$F"         # prove nothing changed
```

Do NOT `rm -rf "$T"` inside the same script: computed-variable recursive deletes are blocked by
the destructive-path safety net. Leave the temp dir, or use a literal path.

Also compare `git ls-remote origin <branch>` against local HEAD **before** claiming a rebase,
reset, or force-push is required. In practice the dirty content was already on the PR head and
no history operation was needed at all.

## 8. Line-delta refresh must reconcile to GitHub

```bash
git fetch --no-tags --quiet origin main
git merge-base HEAD origin/main
git diff --numstat "$(git merge-base HEAD origin/main)" HEAD > /tmp/numstat.txt
```

Classify: production = `mvp_site/**` excluding tests + `.github/**`; everything else
(tests, `testing_mcp/`, docs, tooling) = non-production. Then assert
`prod + nonprod == gh pr view --json additions,deletions`. If the totals disagree, the
classification is wrong — not GitHub.

## 9. Resource gate before any heavy local run

Report numbers, not adjectives: `sysctl -n vm.loadavg` vs `hw.ncpu`, free-memory percentage,
and `df -h` on both `/` and `/System/Volumes/Data`. Two traps seen:

- Load can be 10–20× core count and still be described as "fine"; a load of 173→318 on 14 cores
  means no additional suite should start from that host.
- A disk floor "preserved" reads as *at exactly the floor* (30GiB avail), i.e. zero headroom —
  not "above the floor".

## 10. Local instrument traps (this is where most wrong claims came from)

- **Self-cwd false positive:** a per-PID `lsof -p $p -a -d cwd` loop over all processes reports
  your own shell's `ps`/`lsof`/`grep`/`head` children as "processes bound to the worktree"
  whenever your shell cwd was left inside it. Use one sweep and exclude transient tools:
  `lsof -n -a -d cwd | grep <worktree> | grep -vE "lsof|grep|head|bash"`.
- **`ps -p <pid>` on PIDs harvested from a scan** can return nothing because they were transient
  children — re-scan rather than concluding the process died.
- **Shell cwd persistence:** an earlier `cd` in a persistent terminal session silently changes
  the meaning of every later relative path and every cwd-based attribution.
