# Reading agent-TUI warning/status overlays (Codex) without function keys

Verified 2026-10-24 on codex-cli 0.160.0 panes inside cmux (macOS), two surfaces.

## Trigger

A user pastes cmux/status lines like:

```
- surface:1000100036: … ~/.worktrees/worldarchitect.ai/pr105…  ⚠ 2 warnings · f2 to view
- surface:1000100017: … ~/proj… Goal stalled (/goal resume)    ⚠ 2 warnings · f2 to view
```

`⚠ N warnings · f2 to view` is the **Codex TUI footer**, not a cmux warning. The count is
per-process and identical across panes that share the same launch flags + `CODEX_HOME`.

## What does NOT work

- `cmux send-key --surface … f2` and `… F2` → `Error: invalid_params: Unknown key`.
  `cmux send-key` has no function keys; its accepted set is `enter`, `tab`, `escape`,
  `backspace`, `delete`, `up`, `down`, `left`, `right` (verified this session: `enter`,
  `escape`, `right`, `backspace` all returned `OK`).
- Grepping scrollback for the warning text: the warnings are **not** written to the
  transcript/rollout. `cmux read-screen --scrollback --lines 2000` + `grep -i warn` only
  matched the footer itself. `~/.codex/sessions/**/rollout-*.jsonl` did not contain them either.
- `codex doctor` / `codex doctor --json` is the install/config/auth health surface; it produced
  no startup-warning output here (empty, and hung under a `script` pty, exit 124). Do not use it
  as the read path for TUI warnings.

## What works — the TUI's own local slash command

```bash
# 0. Preconditions: pane is IDLE and composer is EMPTY.
#    Codex idle/empty signature: `› Ask Codex to do anything` + no `Working (Nm • esc to interrupt)`.
#    NEVER do this on a busy pane — typed text QUEUES into that agent's next turn.
cmux read-screen --surface surface:<id> --lines 8

# 1. Type the command and CONFIRM the completion menu names it before submitting.
cmux send --surface surface:<id> "/warnings"
cmux read-screen --surface surface:<id> --lines 10
#    expect a menu row: `› /warnings  view retained warnings and diagnostic details`

# 2. Submit (local command — no provider call, no model turn).
cmux send-key --surface surface:<id> enter
cmux read-screen --surface surface:<id> --lines 45
#    overlay header: `Warnings · 1 of 2 · Startup`
#    footer:        `k keep & next · esc dismiss & close · ctrl+o copy · ←/→ warning · ↓ scroll`

# 3. Page through warnings, then dismiss (not `k`, which keeps the overlay).
cmux send-key --surface surface:<id> right
cmux read-screen --surface surface:<id> --lines 20     # `Warnings · 2 of 2 · Startup`
cmux send-key --surface surface:<id> escape
cmux read-screen --surface surface:<id> --lines 6      # prompt restored, composer empty
```

`/warnings` exists in the slash-command menu; the neighbouring internal name in the binary is
`open_warnings`. `/goal`, `/statusline` etc. behave the same way — these are local TUI commands,
so they are the safe way to inspect TUI state.

## Composer safety (the real hazard)

The dangerous mistake is submitting **prose** into an agent composer: unrecognised text becomes a
model prompt (provider spend — this user gates spend) and can also queue behind a running turn.

- Confirm the slash completion menu shows the exact command before pressing `enter`.
- If you typed into a **busy** pane (footer showed `Sanitizing and publishing campaign data …
  esc to interrupt` and composer hint `tab to queue message`), you have queued text. Do **not**
  press `enter` and do **not** press `esc` (esc interrupts the turn). Clear it with repeated
  `cmux send-key … backspace` — 4 backspaces removed `/war` cleanly and the pane returned to
  running its own turn with an empty composer.
- Disclose any such probe in the reply ("typed and fully backspaced, nothing queued") rather than
  silently leaving it.

## Explaining the warnings from launch flags

`--dangerously-bypass-hook-trust`, `-c`/`--enable`/`--disable` overrides and `--yolo` are what
generate the startup warnings. Tally them from the live process:

```bash
cmux tree | grep -nE 'surface:1000100036|surface:1000100017'   # surface → label/tty/workspace
ps -axo pid,tty,command | grep ttys011 | grep -i codex         # pid for that tty
ps -o command= -p 10225 | grep -oE '\-\-[a-z-]+| -c ' | sort | uniq -c
#   24  -c
#    1  --enable
#    1  --disable
#    1  --dangerously-bypass-hook-trust
#    1  --yolo
```

Observed warning text at codex-cli 0.160.0 (both panes, identical):

1. `Running without the shared background server: command-line configuration overrides (-c,
   --enable, --disable, or --search) requires embedded mode.`
   → cmux injects ~24 `-c mcp_servers.cmux-cua.*` overrides for its computer-use MCP, so embedded
   mode is expected, not a fault.
2. ``--dangerously-bypass-hook-trust` is enabled. Enabled hooks may run without review for this
   invocation.` → standing local-agent setting (cmux/AGENTS launcher), not a finding.

Verdict shape for the user: these are startup/informational, they do not indicate the agent's work
is degraded, and they cannot be silenced without changing the launch flags.

## Receipts to quote

- `cmux send --surface … "/warnings"` then the menu row text, then `Warnings · 2 of 2 · Startup`
  plus the warning body verbatim.
- `ps -o command= -p <pid>` flag tally showing *why* the two warnings exist.
- Final `read-screen` showing the restored prompt (proof you left the pane clean).
