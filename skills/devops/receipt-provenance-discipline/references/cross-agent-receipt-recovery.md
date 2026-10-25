# Cross-agent receipt recovery (recover, never rerun)

When the owner of a PR/lane has already produced RED/GREEN logs, capture traces or video, and a
reviewer asks *you* for those receipts, the job is **retrieval + hashing + publication**. Never
re-run the suite or re-capture to manufacture a receipt — a rerun creates a *new* execution that
does not belong to the owner's claimed run, and it may race the owner's live worktree.

## 1. Where another agent's receipts actually live

| Runtime | Transcript | What to extract |
|---|---|---|
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | `payload.type=="item_completed"` + `item.type=="CommandExecution"` gives the exact `command` array; `function_call_output` / `custom_tool_call_output` carry the stdout |
| Claude Code | `~/.claude/projects/<cwd-with-dashes>/*.jsonl` | assistant messages with `tool_use` name `Bash` → `input.command`; `<persisted-output>` refs point at `tool-results/*.txt` |
| Wrapped runners (`rtk`/tee) | `~/Library/Application Support/rtk/tee/*.log` | jest summaries (`Tests:`, `Test Suites:`, `●` failures), one file per invocation |
| Remote lane worktrees | `ssh <host> 'ls -l --time-style=… /tmp/<task>_*.log'` | the lane's own redirects (`/tmp/<task>_regression-red.log`) usually carry `COMMAND=` and `HEAD=` header lines written by the lane — those are the pin |
| cmux lanes | `cmux list-pane-surfaces --workspace <ws> --json` then `cmux read-screen --surface <ref> --scrollback --lines 1500` | completion markers, "Usage limit reached", queued steer messages |

Surface **refs rotate** (a lane restart changes `surface:1000100015` → `surface:1000100167`);
always re-resolve by `list-pane-surfaces` and match the title, never reuse a stale ref/UUID.

Parse with a small Python script written to a file (`/tmp/scan.py`) and run it. Multi-line
`python3 - <<'PY'` heredocs and long `python3 -c "…"` one-liners are rejected by the command
guard on this host; the fix is a script file, not a retry.

## 2. Recovery checks before you call it a receipt

- **Header pin.** The log itself must carry `COMMAND=` and `HEAD=<sha>` (or the transcript must
  show the pre-run `git show HEAD:<file> > <file>` revert). A log with no pin is an anecdote.
- **Tree binding.** Confirm the worktree was clean at the commit that shipped (`git status
  --short` → only untracked `node_modules`), so "tested tree == committed tree".
- **Time provenance.** Convert and state both zones. On a PDT host `ls --time-style=+%FT%TZ`
  prints **local** time with a literal `Z` — it is not UTC. Derive include/exclude cutoffs from
  `os.path.getmtime()` epochs, never by string-comparing those mislabelled stamps; cross-check
  against the transcript's real `timestamp` field (`…Z`).
- **Claim vs execution.** "Completed `/root/<task>`", a queued cmux message, and a lane saying
  "pass 180/180" are claims. Only a command + output + pin is an execution receipt.
- **Denial vs warning.** A quota/limit *warning* ("less than 5% of your weekly limit left") is not
  a denial. Look for the actual refusal string (`You've hit your session limit · resets …`,
  `Usage limit reached`, `429`). Report the state as "idle/completed" when only a warning exists;
  quote the denial when it does.

## 3. Publishing so a reviewer can inspect it

1. Copy the owner's files verbatim to a local bundle dir; hash **raw** first
   (`shasum -a 256`) and keep the raw hashes in the report.
2. Sanitize: strip ANSI (`\x1b\[[0-9;]*[A-Za-z]`), replace `$HOME`/worktree paths with `<HOME>`/
   `<WORKTREE>`, redact `(password|api_key|secret|bearer)\s*[:=]\s*\S+`. Then grep for
   `xox[abp]-|Bearer [A-Za-z0-9]|BEGIN .*PRIVATE KEY` and require **0** hits.
3. Publish **full 64-hex** sha256 for every shipped file (never a `…`-truncated digest — a
   truncated digest is not independently verifiable), plus the raw hash it came from.
4. Attach text receipts as files, not just fenced blocks, when they are too large to paste and the
   reviewer says "a path/hash description is not inspectable evidence". The Slack
   `files.getUploadURLExternal` → POST → `completeUploadExternal` recipe handles `.log`/`.json`/
   `.md` fine; verify with `conversations.replies` and require `FileCount=1` per upload.
5. Bundle a **source-binding file**: repo, base ref, commit + tree ids, per-file blob id and
   sha256 at both pins, diffstat, artifact hashes, and the observed-behaviour lines. One hashable
   file answers "what exactly was measured" without another round trip.

## 4. Pitfalls that cost a round trip

- A local branch literally named `origin/main` shadows `refs/remotes/origin/main`, so
  `git show origin/main:<path>` reports *"exists on disk, but not in 'origin/main'"* against a
  stale base. Use `refs/remotes/origin/main` or `git rev-parse --symbolic-full-name`.
- `/tmp` is a symlink to `/private/tmp` on macOS; `find /tmp -maxdepth N` silently skips entries.
- `rg` over rollout JSONL can match base64 image payloads and produce thousands of false "jest"
  rows; filter on JSON structure (`item_completed`/`tool_use`) instead of raw text.
- A lane can open a **second** branch/PR while you are recovering (e.g. a narrow standalone
  re-cut). Verify every head with `gh pr view`/`gh ls-remote` per branch and name each one; do not
  assume the PR you were told about is the only artifact in flight.
