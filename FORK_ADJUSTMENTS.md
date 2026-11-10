# Fork Adjustments Registry

Tracks divergence from NousResearch/hermes-agent upstream.
Each entry: what changed, why, upstream PR status, how to verify removal is safe.

## Active adjustments

_None._ Fork main is synced to NousResearch/hermes-agent `upstream/main` at
`4c11aea451` (2026-11-09), plus the local-only files listed below.

**Sync history:** before 2026-11-09 this file claimed parity while fork/main had
drifted **45,398 commits** behind upstream (22,736 files differing). That claim
was stale and is the reason the 2026-11-09 sync exists. Parity claims in this
file decay — re-check with the verification command below before trusting them.

---

## Previously active — now confirmed upstream-merged

| Entry | Was | Status |
|-------|-----|--------|
| `tools/memory_tool.py` render-time truncation | Active | ✅ Upstream has `_char_limit()` + `memory_char_limit` in `_render_block()` |
| `gateway/platforms/slack.py` loop prevention | Active | ✅ Upstream has `SLACK_FREE_RESPONSE_CHANNELS` + `SLACK_REQUIRE_MENTION` |
| `gateway/status.py` macOS `_get_process_start_time` | Active (PR #16) | ✅ Upstream has full psutil + `/proc` fallback |
| `tools/file_operations.py` portable `chmod =rw` | Active | ✅ Upstream has `chmod "=rw"` (confirmed 2026-07-31 via `git show upstream/main:tools/file_operations.py`) |

---

## Local-only (never upstream)

| Item | Reason |
|------|--------|
| `.github/workflows/hermes-pr-tag-listener.yml` | Fork's PR tagging workflow |
| ~~`.coderabbit.yaml`~~ | **Dropped 2026-11-09.** Upstream now ships its own with a documented decision to DISABLE auto-review repo-wide; the fork's copy re-enabled it, contradicting that rationale. Fork uses upstream's. |
| `.gitignore` additions | **Reduced 2026-11-09.** Fork had a wholesale rewrite that would have dropped upstream's required negations (`!hermes_cli/data/`, `!optional-skills/**/examples/`, etc.). Only the `.claude/` token guards were re-applied, appended to upstream's file. |
| `FORK_ADJUSTMENTS.md` | This file |

## How to use this file

- Before rebasing on upstream: check each Active adjustment against the new upstream diff
- Before filing a PR: copy the entry's commit range into the PR body as "addresses FORK_ADJUSTMENTS entry N"
- After upstream merge: move entry from Active to "Previously active — now confirmed upstream-merged"

## Verification command

```bash
# Should return only the 4 local-only files listed above:
git diff upstream/main --name-only
```
