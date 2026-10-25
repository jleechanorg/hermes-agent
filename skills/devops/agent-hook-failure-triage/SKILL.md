---
name: agent-hook-failure-triage
description: Triage "Hook failed"/nonzero hook exits in agent lanes.
version: 1.0.0
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [hooks, codex, claude-code, cmux, triage, diagnostics]
    related_skills: [cmux-surface-steering, harness-plugin-update, launchd-job-forensics]
---

# Agent hook failure triage (Codex / Claude / cmux-launched lanes)

## When to Use

Use when an agent surface shows `• Hook failed`, `hook exited with code N`,
`Hook failed · hook exited with code 1`, or any nonzero hook exit you are asked
to trace while the failing hook is unnamed. Applies to Codex CLI/TUI, Claude Code,
and launcher-injected hooks (cmux, wrappers) where several hook layers run at
once. Also use when an earlier report concluded the hook was "not identifiable
from tail evidence" — that is the expected starting condition, not a dead end.


## Core fact that shapes the whole investigation

**The harness does not tell you which hook failed.** Codex's binary contains only
the literal `hook exited with code ` + number; the hook command/name is omitted
from the UI, and failed hooks are **not** written to `~/.codex/logs_2.sqlite`
(no row contains `exited with code`). Claude Code behaves similarly for
non-blocking hook errors.

**But the rollout often DOES record the denial — read it before anything else.**
When the blocked call went through Codex's custom-tool (`exec`) path, the rollout
`.jsonl` carries a `payload.type == "custom_tool_call_output"` entry whose text
begins `Script failed` / `Script error:` and then quotes the hook's own message
(e.g. `Command blocked by PreToolUse hook: Blocked deletion targeting path …`).
That names the guard AND its reason in one grep (2026-10-24 case:

```
grep -c "Script failed" ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

then pretty-print the matching `payload` — the block reason is in the second
`input_text` item). Only fall through to enumeration/replay when the rollout has
no `Script failed` / `Script error:` record. So:

- Any "identify the hook from the pane tail / from logs" plan is dead on arrival.
- You identify it by **enumerating every registered hook and replaying it**, or by
  **instrumenting a per-hook wrapper** (needs user authorization — see step 6).
- Say this outright in the report; it is why earlier attempts stalled.

Grep proof you can cite:
`sqlite3 -readonly ~/.codex/logs_2.sqlite "select count(*) from logs where feedback_log_body like '%exited with code%'"` → `0`.

## Steps

### 0. Grep the rollout for a recorded denial (cheapest attribution, try first)
For every candidate session on the day, look for `Script failed` and
`Script error:` in the rollout. A hit gives the guard's own message, the blocked
command, and usually the exact false-positive path — no hook enumeration needed.

```python
import json, glob, os, collections
files = sorted(glob.glob(os.path.expanduser('~/.codex/sessions/2026/10/24/*.jsonl')),
               key=os.path.getmtime, reverse=True)
for f in files[:12]:
    for ln in open(f, errors='replace'):
        if 'Script error' not in ln: continue
        s = json.dumps(json.loads(ln).get('payload', {}))
        i = s.find('Script error:')
        print(os.path.basename(f)[:34], '|', s[i:i+220].replace('\\n', ' '))
```

Classify the hits before drawing any conclusion — the same key ("Script failed")
also covers non-hook failures (`SyntaxError` in an `exec` script, `apply_patch
verification failed`, `write_stdin failed: Unknown process id`). Count them
separately so you do not report a JS syntax error as a hook bug.

### 1. Find the lane's real hook inventory (all layers, not just hooks.json)
Codex lanes run **stacked** hook sources. Read all of them:

1. **Launcher-injected hooks** — highest-value source, most often forgotten.
   `ps eww -p <agent_pid>` and read the argv: cmux launches Codex with
   `--enable hooks --dangerously-bypass-hook-trust -c hooks.SessionStart=[…]
   -c hooks.UserPromptSubmit=[…] -c hooks.Stop=[…] -c hooks.PreToolUse=[…]
   -c hooks.PostToolUse=[…] -c hooks.PermissionRequest=[…]`, each pointing at
   `~/.cmux/hooks/cmux-codex-hook-*.sh` (thin `cmux hooks enqueue` wrappers).
   One Bash call in such a lane fires ~6 PreToolUse hooks.
2. **Global file hooks** — `~/.codex/hooks.json` (Claude: the `hooks` object in
   `~/.claude/settings.json`, which is JSONC — strip `//` comments before parsing).
3. **Plugin hooks** — `codex plugin list`, then read each installed+enabled
   plugin's `hooks/codex.json` (e.g. `cc-safety-net` runs
   `node "${PLUGIN_ROOT}/dist/bin/cc-safety-net.js" hook --codex`).
4. **Trust state** — `[hooks.state]` in `~/.codex/config.toml` holds one
   `trusted_hash` per `"<hooks.json path>:<event>:<group>:<index>"`. A hash that
   no longer matches means the script was rewritten after trust was granted; an
   extra `0:4` entry on a 4-hook group is evidence of a since-removed hook.

### 2. Probe each hook standalone
Feed a harness-shaped payload on stdin; record **rc + stdout + stderr**.
Codex PreToolUse shape:
`{"session_id":"s","transcript_path":"/tmp/t.jsonl","cwd":"<real path>","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"/bin/bash -lc 'echo hi'"}}`
Also probe empty stdin, malformed JSON, and a ~200 KB payload — fail-closed
guards often differ there.

**Exit-code semantics:** `0` = pass · `2` = intentional deny/block (correct
behaviour, NOT the bug) · `1`/`127` = the failure you are hunting
(`127` = executable missing from the hook's restricted PATH).

### 3. Replay the real workload
Benign payloads prove nothing. Pull the commands the failing session actually ran:
- Source: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, lines with
  `payload.type == "item_completed"` → `item.type == "CommandExecution"` →
  `item.command` (a list; join it), plus `item.cwd` (often a `file://` URL).
- **Also replay the `custom_tool_call` items** (`payload.type ==
  "custom_tool_call"`, fields `name` + `input`) and match them by `call_id` to
  their `custom_tool_call_output`. These carry the raw JS/`exec` source, not a
  plain shell string, and guards parse that source differently: a hand-built
  `{"tool_name":"Bash","tool_input":{"command":"<the shell cmd>"}}` payload can
  return `rc=0` while the recorded `exec` source returns `rc=2` deny, because the
  guard sees quoted `"$VAR"` inside the JS and resolves it to a bogus relative
  path. Replay the recorded `name` + `input` verbatim; a synthetic payload that
  passes proves nothing about the lane.
- Run `scripts/replay_hooks.py` (in this skill): tabulates rc per hook per command
  and prints a sample of every nonzero with stdout/stderr.
- 150+ real commands × every hook all `rc=0` is a defensible negative: none of the
  currently registered hooks can produce the observed failure.

### 4. Live replay with the identical hook chain
Reproduce end-to-end instead of trusting standalone runs:

```
RUST_LOG=codex_core=debug codex exec --skip-git-repo-check -s danger-full-access \
  -C <failing cwd> --enable hooks --dangerously-bypass-hook-trust \
  -c 'hooks.PreToolUse=[{hooks=[{type="command",command="'''<script>'''",timeout=5000}]}]' \
  "Run exactly this one shell command then stop: echo hi"
```
Grep the output: one `hook: PreToolUse` / `hook: PreToolUse Completed` pair per
hook, in order. A missing `Completed` or an `exited with code` line is the repro.
Build the `-c` value with `chr(39)*3` for `'''` — writing `'''` inside a Python
f-string is a syntax error.

### 5. Reason about time and pasted text before concluding
- Compare failure **timestamps** with the mtime of the hook scripts. Scripts
  rewritten at T do not explain failures stamped before T.
- Panes are full of **pasted transcripts**: a user pasting an earlier report back
  into a prompt reproduces `• Hook failed` lines with no timestamp and no tool
  call. Count only timestamped, non-quoted events — a 190-hit pane can be ~0 live
  events.
- Position is a clue: failures before the first tool call implicate
  `SessionStart` + `UserPromptSubmit`; failures interleaved with `Ran …` items
  implicate `PreToolUse`/`PostToolUse`.

### 6. When still unidentified: instrument, don't guess
Only a per-hook wrapper logging `hook path / rc / stderr / stdin digest` can
attribute the failure, because the harness drops the name. That means editing the
live hook invocation (launcher argv or a hook script) — state the exact edit and
get authorization first. Do not silently rewrite the user's hooks to chase a
diagnostic.

## Pitfalls
- cmux `read-screen` needs prefixed refs: `--surface surface:1000090001`. A bare
  numeric id returns `Error: Surface index not found`. Use `cmux tree --all` to map
  workspace/pane/surface ids to titles and ttys; `list-workspaces` is an alias of
  `cmux workspace list`.
- `ps eww` splits values on spaces, so `/Applications/cmux DEV dev-fork.app/…`
  looks truncated. Confirm with `cmux identify` before concluding a binary is
  missing.
- A guard returning `2` can render as a generic hook error in some UIs; verify rc
  yourself before calling a guard broken.
- `stop-hook-dispatch.sh` and `conflict-warn-pre-tool.sh` carry `set -euo pipefail`;
  an internal non-zero becomes an exit 1 with no message. Check those first among
  "global" hooks.
- Wrapper hooks shaped `cli … 2>/dev/null || { cat >/dev/null; echo '{}'; }` can
  never return nonzero — they mask failures and always print `{}`. Their silence
  is not health; test the underlying `cli hooks enqueue …` call directly.
- **Never classify an interleaved `Hook failed` as "noise, the lane is still
  progressing."** Progress on *other* tools says nothing about the blocked one.
  In the 2026-10-24 case the "noise" was a fail-closed guard denying 49 real
  `exec` calls, including the ffmpeg frame-extraction step that produced PR
  evidence. Recover the denial reason (step 0) before using the word noise.
- **Check installed-vs-exported drift before promising a fix.** `~/.codex/hooks/`
  is not a git repo; the repo export lives at `~/projects/jleechan-skills/.codex/hooks/`
  and can be *older* than what runs. Compare `shasum -a 256` on both and report
  which one is live; a merged PR to the stale export does not change behaviour.
- A guard's *allowlist roots* are the usual false-positive source. Grep the
  script for its roots (`grep -nE "ALLOW|allow_roots|projects"`), then prove the
  gap with one allow-path vs one deny-path `rm` probe from the same cwd. Repo
  trees outside the roots (`~/project_worldai_frontend`, `~/projects_other`) deny
  every in-tree delete.
- Do not call a hook broken because its script mtime is recent. Test it.

## Verification / reporting
Report: lane and pid, the complete hook inventory, the replay matrix (hooks ×
commands, all exit codes), the live-replay result, and — if unresolved — that
attribution is impossible without instrumentation, with the named next step.
Never upgrade "not reproducible" into "fixed".

## Support files
- `references/codex-cmux-hook-layers.md` — file locations, hook naming, payload
  shapes, and the 2026-10-22 cmux hook-rewrite case study.
- `references/codex-rollout-script-error-attribution.md` — the rollout
  `Script failed` / `Script error:` extraction recipe, the `custom_tool_call`
  replay pattern, and the 2026-10-24 `path-deletion-guard` allowlist case.
- `scripts/replay_hooks.py` — replay a session's real commands across every hook
  and tabulate exit codes.
