# Codex / cmux hook layers — locations, shapes, case study

## Where everything lives (macOS, Codex 0.160.0)

| What | Path |
|---|---|
| Global Codex hooks | `~/.codex/hooks.json` |
| Global Codex hook trust hashes | `~/.codex/config.toml` → `[hooks.state]` |
| Session rollouts (commands, tool items) | `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` |
| Structured logs (app-server events, warnings) | `~/.codex/logs_2.sqlite` (table `logs`) |
| Desktop/app-server logs | `~/Library/Logs/com.openai.codex/YYYY/MM/DD/*.log` |
| cmux-injected hook scripts | `~/.cmux/hooks/cmux-codex-hook-<hash>-<event>.sh` |
| Plugin hook manifests | `~/.claude/plugins/cache/<marketplace>/<plugin>/<ver>/hooks/codex.json` |
| Claude hooks | `~/.claude/settings.json` → `hooks` |
| Claude transcripts | `~/.claude/projects/<slug>/<session>.jsonl` |

`codex --version`, `codex doctor`, `codex plugin list`, `codex debug …` are all
read-only and useful for inventory; `codex doctor` is slow (~2.5 min) so prefer
targeted greps first.

## Layered hook model for a cmux Codex lane

`ps eww -p <pid>` argv is the authoritative inventory. Observed shape:

```
codex --disable computer_use … --enable hooks --dangerously-bypass-hook-trust
  -c hooks.SessionStart=[{hooks=[{type="command",command='''…/cmux-codex-hook-<h>-session-start.sh''',timeout=5000}]}]
  -c hooks.UserPromptSubmit=[{…prompt-submit.sh…},{…inbox-drain.sh…}]        # 2 hooks
  -c hooks.Stop=[{…stop.sh…},{…inbox-stop.sh…}]                             # 2 hooks
  -c hooks.PreToolUse=[{…pre-tool-use.sh…}]                                 # +4 from hooks.json +1 plugin
  -c hooks.PostToolUse=[{…post-tool-use.sh…}]
  -c hooks.PermissionRequest=[{…notification.sh…,timeout=120000}]
  resume <session-uuid>
```

So a single Bash call can fire **6 PreToolUse hooks**: 4 from `~/.codex/hooks.json`
group 0 (`diskm guard-worktree-add`, `path-deletion-guard.py`,
`block-home-scan.sh`, `rtk-hook-guard.sh`), 1 marketplace plugin
(`cc-safety-net … hook --codex`), 1 cmux enqueue wrapper. Session/prompt/stop
events add 1–2 cmux hooks each.

Watch for `-c hooks.<Event>` **replacing** vs **appending to** the file hooks —
verify by counting `hook: PreToolUse` lines in a debug replay, not by reading
config alone.

## Why the name is missing

`strings <codex binary> | grep 'hook exited'` yields the bare literal
`hook exited with code ` — no command interpolation. Failed hooks also produce no
row in `logs_2.sqlite` (`feedback_log_body` never contains `exited with code`)
and no item in the rollout. Claude Code renders non-blocking hook errors the same
way. Conclusion: attribution requires instrumentation or exhaustive replay.

`--dangerously-bypass-hook-trust` suppresses trust prompts but still prints
`warning: … enabled hooks may run without review`; that warning is not a failure.

## Case study — 2026-10-22/23, surface "codex" in cmux workspace `disk`

Symptom: ~190 `• Hook failed / └ hook exited with code 1` renderings in
`surface:1000090001` (cwd `~/projects_other/worktree_dropbox`, Codex 0.160.0,
pid 86096 → 86167), plus 4 in a fresh session immediately after prompt submit.

What the investigation established:

- 150 real commands from that session's rollout × 6 hooks = **900 invocations,
  all rc 0**; 250 commands × 5 Claude-path hooks = **all rc 0**; empty,
  malformed-JSON and 200 KB payloads also clean (only the fail-closed guards
  returned `2`, which is their designed deny).
- Live `codex exec` with the identical `-c hooks.*` chain in the same cwd:
  `hook: PreToolUse` ×6, all `PreToolUse Completed`.
- The final failures in the pane had **no timestamp** — they were a pasted copy
  of an earlier report inside a user prompt. Latest real event
  `2026-10-23T05:58:40Z`, and the hook scripts under `~/.cmux/hooks` were
  rewritten `2026-10-22 22:45 PDT`.
- Remaining ranked suspect: the cmux enqueue wrappers, because (a) in the fresh
  session the failures appear 3× before any tool call — matching
  `SessionStart` ×1 + `UserPromptSubmit` ×2 — and (b) those wrappers end in
  `2>/dev/null || { cat >/dev/null; echo '{}'; }`, so they mask their own
  failures. Directly running `cmux --socket <sock> hooks enqueue codex
  pre-tool-use` returns `{}` rc 0 today.

Verdict delivered: not reproducible from the current hook generation, name not
attributable without a logging shim; a one-time recheck cron was scheduled rather
than declaring a fix.

## Instrumentation option (needs authorization)

Wrap each hook command as `sh -c '<real-hook> ; rc=$?; printf "%s rc=%s\n"
"<hook path>" "$rc" >> /tmp/hookshim.log; exit $rc'` (or the equivalent
`-c hooks.<Event>` edit in the launcher argv), reproducing stdin untouched via
`tee`. Recall that a prior attempt at this existed as `/tmp/hookshim.py` /
`/tmp/hook-diag.sh` and had already been cleaned up when re-examined — put the
logs somewhere durable and record the path in the report.
