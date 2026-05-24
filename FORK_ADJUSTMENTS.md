# Fork Adjustments Registry

Tracks divergence from NousResearch/hermes-agent upstream.
Each entry: what changed, why, upstream PR status, how to verify removal is safe.

## Active adjustments

### 1. `tools/memory_tool.py` — render-time truncation in `_render_block()`

| Field | Value |
|-------|-------|
| File | `tools/memory_tool.py` |
| Commit | `f0a00fd94` |
| Category | bug-fix |
| Upstream PR | pending (GH rate limit — file when reset) |
| Removable when | upstream merges and we rebase |

**Root cause:** `_render_block()` injected all entries without truncation.
`memory_char_limit: 2200` guarded writes only. File grew to 422KB / 4,318 entries → 118k tokens per session.

**Verify safe to remove:** `grep -A5 '_render_block' tools/memory_tool.py | grep 'kept\|reversed'` — if upstream has this, our patch is redundant.

---

### 2. `gateway/platforms/slack.py` — config-driven bot loop prevention

| Field | Value |
|-------|-------|
| File | `gateway/platforms/slack.py` |
| Commits | `1edbea4de`, `9543613fc`, `38cadf794`, `current` |
| Category | feature/config |
| Upstream PR | ready to file — generic, no hardcoded IDs |
| Removable when | upstream merges; our IDs stay in plist env vars |

**Root cause:** sibling Hermes instances (prod + staging) sent each other messages in loops.
Fix: `SLACK_LOOP_BLOCK_USERS`, `SLACK_LOOP_BLOCK_BOTS`, `SLACK_LOOP_BLOCK_NAMES` env vars.
Our specific IDs live in `~/Library/LaunchAgents/ai.hermes.prod.plist`.

**Verify safe to remove:** `grep SLACK_LOOP_BLOCK gateway/platforms/slack.py` — if upstream has it, our patch is redundant but env vars still work.

---

### 3. `gateway/status.py` — macOS `_get_process_start_time` support

| Field | Value |
|-------|-------|
| File | `gateway/status.py` |
| Commit | `0ac71e12b` |
| Category | bug-fix / portability |
| Upstream PR | filed as PR #16 |
| Removable when | upstream PR #16 merges |

**Root cause:** `_get_process_start_time` used Linux-only `/proc` — crashed on macOS.

**Verify:** `grep -n 'proc\|darwin\|platform' gateway/status.py | head -5`

---

## Local-only (never upstream)

| Item | Reason |
|------|--------|
| `.github/workflows/green-gate.yml` | Our 6-gate CI harness — project-specific |
| `.github/workflows/skeptic-cron.yml` | Our auto-merge cron — project-specific |
| `.coderabbit.yaml` | Our CR config |
| `optional-skills/` RTK plugin | Env-specific (RTK token rewriting) |
| `.gitignore` additions | AO session files — harmless upstream but unnecessary |

## How to use this file

- Before rebasing on upstream: check each Active adjustment against the new upstream diff
- Before filing a PR: copy the entry's commit range into the PR body as "addresses FORK_ADJUSTMENTS entry N"
- After upstream merge: delete the entry and verify with the "Verify safe to remove" command
