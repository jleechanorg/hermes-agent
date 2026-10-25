# pr-green report: "N dispatch failures" = 2 permanently wedged PRs (2026-10-24)

Seventh consecutive pr-green report thread. The posted 4h report looked benign
(`dispatched 0`, `dispatch failures 16`, `delivery-unconfirmed 2`) and the real
state was: **two merge-conflict PRs have been un-dispatchable for 7–13 days**,
and every sweep since at least 02:35 PDT re-selected them, burned both
dispatch slots, and logged the same generic line.

## 1. Disaggregate the report before believing its shape

The report counts **rows**, not targets. Never read `dispatch failures 16` as
16 distinct failures.

```bash
ssh jeff-ubuntu 'cd ~/.local/state/jleechanorg-pr-green && python3 - <<"EOF"
import json,collections,time,datetime
rows=[json.loads(l) for l in open("outcomes.jsonl") if l.strip()]
# epoch-seconds fields: ts, run_ts   (NOT iso strings)
rows=[r for r in rows if r.get("ts") or r.get("run_ts")]
now=max(r.get("ts") or r.get("run_ts") for r in rows)
recent=[r for r in rows if (r.get("ts") or r.get("run_ts"))>now-4*3600]
print(dict(collections.Counter(r.get("result") for r in recent)))
fails=[r for r in recent if "dispatch" in str(r.get("result","")).lower()]
print("rows",len(fails),"distinct PRs",sorted({r.get("number") for r in fails}))
print(collections.Counter(str(r.get("detail"))[:60] for r in fails).most_common(5))
EOF'
```

Key shape facts for `outcomes.jsonl` (22k+ rows accumulate here):

- The outcome field is **`result`**, not `outcome` / `classification`
  (`Counter(r.get("outcome"))` returns `{None: N}` and looks like a clean sweep — it is not).
- Rows also carry `repo`, `number`, `url`, `head_before`, `head_after`,
  `blocker_before`, `session_action`, `native_ack_status`, `verified`.
- `ts` / `run_ts` are epoch **seconds**; ISO conversion of them fails silently
  and yields an empty "recent" window.
- One row per PR per sweep → a 30-minute cadence makes 8 sweeps × 2 PRs look
  like "16 failures".

## 2. The actual defect: silent `return 4` on a stale Chat pending marker

`~/projects/dark-factory/jobs/jleechanorg-pr-green/session-reuse.sh`, inside
`pr_green_reuse_session()` chat-mode exited branch:

```bash
chat_pending="$(pr_green_delivery_pending_path "$project_id" "$pr_number")" || return 4
[[ ! -e "$chat_pending" && ! -e "${chat_pending}.chat" ]] || return 4    # line ~1255
```

A pre-existing `.chat` marker returns 4 with **no `>&2` line, no age check,
and no clear/expire path**. Because the caller captures the function in
`$(...)`, only the caller's stdout survives; the journal shows nothing but:

```
[pr-green-daily] selected worldarchitect.ai#10098
[pr-green-daily] delivery unconfirmed for worldarchitect.ai#10098; duplicate spawn suppressed
```

Marker layout: `$METRICS_DIR/pending-delivery/<project>-<pr>.json` plus
`<...>.json.chat` (chat-mode delivery receipt). `METRICS_DIR` defaults to
`~/.local/state/jleechanorg-pr-green`.

Proof of staleness (do not dump marker bodies — they contain the repair prompt):

```bash
python3 -c 'import json,os,time;d=json.load(open(p));print(d.get("session"),len(d.get("text") or ""),(time.time()-os.stat(p).st_mtime)/86400)'
```

Observed: `worldarchitect.ai-10098.json.chat` mtime 2026-10-10 23:33 (13.3 d),
`-10549.json.chat` 2026-10-16 12:31 (7.8 d), both bound to AO sessions
`worldarchitect.ai-96` / `-185` that `ao session get` reports `status: exited`
(updated 7–14 days ago). `native-runtime.py --mode ~/.ao/data/ao.db <project> <session>`
returns `chat` for both, which is what routes them into the fragile branch.

Both PRs were still `OPEN` + `mergeable: CONFLICTING` with unchanged heads —
exactly the population the sweeper exists to repair.

## 3. Finding which branch/commit a lane really runs

A posted report can only be interpreted against the code that actually ran.
The lane was executing an **unmerged feature branch**, not `origin/main`:

```bash
systemctl --user cat jleechanorg-pr-green-daily.service | grep -E 'ExecStart|WorkingDirectory'
#  → /home/jleechan/.hermes/scripts/systemd-wrapper.sh %h/projects/dark-factory/jobs/jleechanorg-pr-green/run.sh
cd ~/projects/dark-factory && git status -sb && git log --oneline -1
git rev-list --left-right --count origin/main...HEAD      # 16  86
git branch -r --contains <head-sha>                       # which PRs carry this code
git show origin/main:jobs/jleechanorg-pr-green/session-reuse.sh | grep -n 'pr_green_chat_delivery()'
#  → no match: the whole Chat delivery path is absent from main
```

Consequence: "fix it on main" is not available. The only carrier was draft PR
#853 (`fix/pr-green-stale-chat-worktree`), whose own tests `rm -f` the `.chat`
marker before exercising restore — i.e. the starvation hole survives that PR.
Check the carrier PR's diff for the marker handling before assuming a fix exists:
`gh pr diff <n> | grep -n "chat_pending\|\.chat"`.

## 4. Diagnosing silent bash `return N` paths

When a shell function returns a code with no stderr, do not expect the journal
to name the branch. Instead:

1. Enumerate every `return <N>` in the function and tag each **silent** vs
   `>&2`-emitting (grep `-n` with context; the caller's rc dispatch is separate).
2. Match remaining silent candidates against on-disk state (which marker files
   exist) and DB/CLI state (`ao session get`, `native-runtime.py --mode`).
3. Re-run only read-only probes — never source the job script or invoke the
   reuse function directly, because its happy path **restores a session and
   sends a prompt**.

## 5. Remediation shape (durable, not a live poke)

Reported patch shape, filed as bead `rev-d2484y` in dark-factory with
file:line, marker ages, session IDs and run evidence:

- Exited/terminated chat session + marker older than a bounded TTL + no live
  native user turn → **archive** the marker (`<...>.chat.stale-<ts>`) and
  continue to restore+deliver.
- Otherwise keep the hold, but emit a **named stderr reason** and a distinct
  outcome so the next report can classify it.
- Do **not** hand-delete production markers as an unprompted "fix": restoring
  a 7-day-dead session and prompting it is a behavioural change to live
  dispatch, and it hides the latent hole. Name it as the manual unblock; land
  the TTL fix.

## 6. Pitfalls

- `Counter(r.get("outcome"))` → `{None: 280}`. The field is `result`.
- Counting `selected` as attempts: `selected 9 / attempted 0 / dispatched 0`
  means the reuse guard fired, not that there was nothing to fix.
- Grepping journal for `native|rollout|identity` finds nothing when the silent
  branch fired — absence of a message is the signal, not a dead end.
- `git branch -r --contains` is how you learn a fix belongs on a draft PR
  rather than a fresh branch off main.
