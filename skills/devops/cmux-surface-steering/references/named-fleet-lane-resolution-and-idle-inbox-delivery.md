# Named fleet lanes: resolve → deliver → prove pickup (verified 2026-10-24)

A peer asks you to "route this to the existing Luna2 / fleet_shard_2 lane, not the
auto-creation log-tail pane". Three separate problems hide in that sentence: the name is
not a cmux title, one of the candidate panes cannot receive *anything*, and an idle lane
never drains its cmux inbox on its own. All three were hit and solved in one session.

## 1. A lane NAME is not a surface handle

`cmux tree --all | grep -i luna2` → nothing. Workspace/surface titles are human labels
(`creation ui`, `worktree_autocrrstion`); fleet names (`fleet_shard_2`, `Luna2`) live in
the orchestrator's own bookkeeping. Resolve through the agent's session JSONL instead:

```bash
# which codex sessions mention the lane name, and what cwd/model do they belong to?
cd ~/.codex/sessions/$(date -u +%Y/%m/%d) && python3 - <<'PY'
import json,glob
for f in sorted(glob.glob('rollout-*.jsonl')):
    n=0
    with open(f,errors='replace') as fh:
        meta=json.loads(fh.readline() or '{}')
        for line in fh:
            if 'fleet_shard_2' in line: n+=1
    if n:
        p=meta.get('payload',{})
        print(f, 'hits=',n, 'cwd=',p.get('cwd'), 'session=',p.get('id'))
PY
```

Two outputs matter:

- the `cwd` maps to a cmux lane — `cmux tree --all | grep <worktree-name>` and/or
  `lsof -n -d cwd | grep <worktree-name>` give the surface + owning pid;
- a session file whose mtime is *now* is an active lane; an old one is history.

**Subagent lanes (`/root/fleet_shard_2` notation) have no inbox of their own.** They are
ephemeral children of a parent Codex session (`collaboration.followup_task` /
`list_agents`). The only addressable route is the parent session's surface; the parent
then hands to the lane. Say that in the receipt instead of hunting for a surface that
does not exist.

## 2. Log-tail panes: identify by tty argv, never by title

`ps -t ttysNNN -o pid=,etime=,command=` is the discriminator:

```
1574 -/bin/bash
99402 tail -n 40 -f /tmp/worldai-p1-drive.sHOFC8Ya/autocreation-recovery.md
```

That pane is a **mirror** of a file, with no CLI and no agent. `cmux send` / `agent
message` land as inert shell text there; a pointer echo in that surface is decorative and
must never be counted as delivery. Same check catches the sibling failure: only
`/usr/bin/login` + `-/bin/bash` on the tty means the agent exited.

## 3. Queued on an idle lane never becomes delivered

`cmux agent message` reaches the agent through its hooks: `delivered_via` is
`codex.prompt-submit` when the agent takes a turn and `codex.stop` when it finishes one.
An agent that is idle with a stalled goal takes **no events**, so the message sits at
`state=queued` forever. Observed: message stayed `queued` for ~4 min until a turn was
submitted, then delivered 50 s later and read 2 min after that.

Eligibility gate before typing (all four, else stay inbox-only and say which failed):
idle tail (no `Working… / esc to interrupt`), empty composer (`› Ask Codex to do
anything`, no `Queued follow-up inputs`), not quota/goal-stalled in a way that refuses
input, and correct target (workspace + surface + cwd + branch).

```bash
cmux agent message --from hermes surface:<S> - < /tmp/brief.md      # body from a file
cmux send --surface surface:<S> "Read queued cmux agent message <id> from hermes (<topic>) and hand it to the existing <lane>. Preserve that lane as sole source owner: no new writer, no new capture/provider run, no assertion weakening, no merge."
cmux send-key --surface surface:<S> enter
cmux agent inbox --surface surface:<S> --json      # state / delivered_via / delivered_at / read_at
cmux read-screen --surface surface:<S> --lines 90  # the agent's own restatement
```

Keep the pointer ONE line that names the queued id and the ownership limits; the brief
itself is already in the inbox. The nudge is what creates the `codex.prompt-submit` event.

## 4. Receipt ladder — do not collapse the rungs

| rung | evidence | means |
|---|---|---|
| addressed | `Queued message <uuid>` | an id exists |
| delivered | `state=delivered`, `delivered_via=codex.prompt-submit` | reached the hook queue |
| read | `state=read`, non-null float-epoch `read_at` | agent consumed it |
| acted | pane restatement / handoff receipt file / `Completed /root/<lane>` | agent moved it |
| done | source artifact (commit, PR comment, published ledger) | the work exists |

The parent will usually write its own handoff receipt (`/tmp/<topic>-hermes-handoff.*/receipt.md`);
read it and quote it. A receipt that says *"explicit pickup acknowledgment remains pending;
running status does not prove completed artifact work"* is the correct, honest rung —
report it that way. `Completed /root/<lane>` in the pane is rung 4, not rung 5, and the
lane's ack text may legitimately never appear.

## Pitfalls

- `ps -axo …` (whole-system, long command column) can exceed a 180 s foreground timeout on
  a busy Mac; use `pgrep -fl`, `ps -t ttysNNN`, or `lsof -d cwd` instead.
- `cmux agent inbox` with no target errors (`Give a target workspace or surface`) when
  called from outside a cmux surface — always pass `--surface`.
- `cmux agent messages status <target>` needs the target as a positional; `--surface`
  there is a usage error.
- Do not "fix" a queued message by re-sending: it becomes a second message id and a
  duplicate instruction to a lane that may already be executing.
