# Localising "Hook failed / hook exited with code 1" (Codex TUI)

Symptom: a codex surface shows `Hook failed` / `hook exited with code 1` repeatedly, and the
owning lane reports "the failing hook is still unidentified" after poking at config.

The message is rendered **only in the TUI**. It is not written to
`~/Library/Logs/com.openai.codex/**` and does not appear in
`~/.codex/sessions/**/rollout-*.jsonl`, so grepping those logs for "hook failed" returns nothing
and can be mistaken for "no failure happened".

## 1. Enumerate the hooks that can actually fire

```bash
python3 -c "import json;print(json.dumps(json.load(open('/Users/<u>/.codex/hooks.json')),indent=1))"
# per-repo overlay, if any (often only SessionStart + Stop, no PreToolUse):
cat <worktree>/.codex/hooks.json
```

Do this first: a repo overlay with no `PreToolUse` block means the per-tool-call failures can
only come from the global file — which halves the search space.

## 2. Replay each hook by hand with a synthetic payload

Write ONE payload file, then feed it with a literal command per hook:

```bash
printf '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo hi"}}' \
  > /tmp/hookprobe.json
diskm guard-worktree-add                                < /tmp/hookprobe.json; echo rc=$?
python3 ~/.codex/hooks/path-deletion-guard.py           < /tmp/hookprobe.json; echo rc=$?
bash ~/.claude/hooks/block-home-scan.sh                 < /tmp/hookprobe.json; echo rc=$?
bash ~/.codex/hooks/rtk-hook-guard.sh                   < /tmp/hookprobe.json; echo rc=$?
```

Repeat with an `apply_patch` payload for the patch matchers
(`path-deletion-guard.py`, `conflict-warn-pre-tool.sh --runtime codex`).

Write the commands out literally. A loop like `for c in ...; do bash -c "$c"; done` is refused by
the shell safety net (`analysis.dynamic-shell-source`), costing a round trip.

## 3. Reproduce end-to-end in a fresh headless session

Manual replays can all exit 0 while the interactive session still fails (state, cwd, or payload
shape differs). Force a real hook lifecycle including a tool call:

```bash
cd <affected-worktree> && codex exec -s read-only \
  "Run exactly one shell command: echo hi. Then reply DONE."
```

Readiness line sequence to expect on success:

```
hook: SessionStart ... Completed
hook: PreToolUse x N ... Completed
exec /bin/bash -lc 'echo hi' ... succeeded
hook: Stop ... Completed
```

If that prints `Completed` with no `Hook failed`, the hooks are **not** globally broken: the
failure is specific to the parked session's state (deleted cwd, reset worktree, stale trust hash).
Say "not a global config break; needs that surface's live session context" rather than leaving a
config-fix that changes behavior for every lane.

## Pitfalls

- Diagnostic shims under `/tmp` (`hookshim.sh`, `hookshim.log`) do not survive: if a handoff cites
  them, treat the evidence as unrecoverable and re-derive rather than trusting the summary.
- `~/.codex/config.toml` `[hooks.state."...:pre_tool_use:0:0"] trusted_hash = ...` records the hash
  of a previously approved hooks file; editing `hooks.json` invalidates trust. Check the file's
  mtime against the session start before blaming the hook body.
- Do not conclude "hook is broken" from a nonzero exit that is the guard's intended block
  (e.g. a blocked `rm`). Distinguish block-with-message from crash.
- Never classify the surface from a short tail: capture `--scrollback --lines 1000+` first
  (see the full-buffer rule), then grep the whole capture for `hook`.
