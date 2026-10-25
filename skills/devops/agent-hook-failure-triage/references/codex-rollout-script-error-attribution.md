# Attributing `Hook failed` via the Codex rollout — recipe + 2026-10-24 case

## Why this file exists

`agent-hook-failure-triage` used to say failed hooks are never written to the
session rollout. That is wrong for calls that go through Codex's custom-tool
(`exec`) path: the rollout keeps the guard's denial message verbatim. This file
holds the extraction recipe and the case that proved it (49 blocked calls in one
day, mis-reported upstream as "hook noise").

## Extraction (copy-paste)

```python
import json, glob, os, collections
files = sorted(glob.glob(os.path.expanduser('~/.codex/sessions/2026/10/24/*.jsonl')),
               key=os.path.getmtime, reverse=True)
causes, perfile = collections.Counter(), collections.Counter()
for f in files[:12]:
    for ln in open(f, errors='replace'):
        if 'Script error' not in ln:
            continue
        try:
            s = json.dumps(json.loads(ln).get('payload', {}))
        except Exception:
            continue
        i = s.find('Script error:')
        txt = s[i:i+300].replace('\\n', ' ')
        if 'Command blocked by PreToolUse hook' in txt:
            key = 'PreToolUse BLOCK'
        elif 'write_stdin failed' in txt:
            key = 'write_stdin unknown process id'
        elif 'SyntaxError' in txt:
            key = 'exec JS syntax error'
        else:
            key = 'other: ' + txt[:90]
        causes[key] += 1
        perfile[os.path.basename(f)[:34]] += 1
print(causes.most_common(8))
```

Then find the matching call and its input:

```python
target = 'call_<id from the output entry>'
for ln in open(f, errors='replace'):
    if target in ln:
        print(json.dumps(json.loads(ln)['payload'])[:2500])
```

`custom_tool_call` → `name` (`exec`) + `input` (the JS source).
`custom_tool_call_output` → `output[0].text` = `Script failed / Script error: …`.

## Replay the recorded payload (do NOT hand-build one)

```python
import json, subprocess
payload = json.dumps({
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",              # and try the recorded name, e.g. "exec"
    "cwd": "<item.cwd, file:// prefix stripped>",
    "tool_input": {"command": "<recorded custom_tool_call.input verbatim>"},
})
p = subprocess.run(["python3", "<hook script>"], input=payload,
                   capture_output=True, text=True)
print(p.returncode, (p.stdout + p.stderr)[:400])
```

Exit semantics seen here: `0` pass, `2` = intentional deny (the guard prints
`{"hookSpecificOutput":{"permissionDecision":"deny", ...}}`), and the TUI
flattens `2` into the generic `Hook failed / hook exited with code 1`.

## Case: `path-deletion-guard.py`, 2026-10-24

Lane: `surface:1000100015` / workspace "creation ui", codex `exec` tool, cwd
`~/project_worldai_frontend/worktree_ios_creation_flow`.

Blocked command (abridged):

```
ssh jeff-ubuntu 'set -e; M=/tmp/worldai_frontend/evidence/preflow-580-media-20261024;
  rm -f "$M"/inspect-*.jpg; ffmpeg … "$M/inspect-baseline.jpg" -y; ls -lh "$M"/inspect-*.jpg'
```

Deny reason quoted by the guard:

```
Blocked deletion targeting path outside project/temp allowlist:
/Users/jleechan/project_worldai_frontend/worktree_ios_creation_flow/M/inspect-baseline.jpg,
…/M/inspect-candidate.jpg, …/M/inspect-stream-failed.jpg
```

Two independent defects:

1. **Allowlist gap.** `DEFAULT_ALLOW_ROOTS` = `$HOME/projects`,
   `$HOME/.worktrees`, `/tmp`, `/private/tmp`, `/var/folders`.
   `~/project_worldai_frontend` and `~/projects_other` are missing, so *any*
   `rm` inside those real repo trees is denied. One-probe proof:
   `rm -f ~/projects/worldarchitect.ai/tmp/x.jpg` → rc 0;
   the identical shape under `~/project_worldai_frontend/…` → rc 2 deny.
2. **Unresolved variable → fabricated path.** In the `exec` source the parser
   drops `"$M"` to empty, keeps the literal token `M/inspect-*.jpg`, resolves it
   against cwd and denies that synthetic path. It also ignores that the `rm`
   targets a **remote** host (`ssh jeff-ubuntu`), so the local allowlist does not
   apply at all.

Blast radius: 49 `Command blocked by PreToolUse hook` outcomes across 6 codex
rollouts that day, surfacing in the TUI as undifferentiated `Hook failed`. In the
creation-ui lane it blocked the ffmpeg frame-extraction step that produces the
BEFORE/AFTER `inspect-*.jpg` images for PR evidence.

Secondary findings worth checking in any hook triage:
- `~/.codex/log/path-deletion-guard.log` grows unbounded (25 MB / 219,295 lines,
  no rotation) — it is an audit log, one line per Bash call, so it is *not* the
  failure log and its tail will mislead you.
- Installed `~/.codex/hooks/path-deletion-guard.py` (`fc42ae96…`, 632 lines) was
  newer than the repo export `~/projects/jleechan-skills/.codex/hooks/…`
  (`d932352e…`, 478 lines, temp-only allowlist). Always sha256 both and say which
  one is live.

Fix shape (policy signoff required): allow roots from a config file rather than
code, treat unresolvable `$VAR` / remote targets as resolvable-with-note instead
of deny, rotate the log, and resync the stale export.

## Reporting line that survived review

> The report's "hook noise" classification is wrong — I reproduced the guard: it
> denies every `rm` under `~/project_worldai_frontend`, and it turns `"$M"` into a
> literal relative path. 49 blocks today, including the evidence-frame step.

State the classification change explicitly; do not bury a corrected verdict in a
"noted" bullet.
