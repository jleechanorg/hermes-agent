# Named-lane routing and receipt path checks (worked recipes)

Session case 2026-10-24: peer asked to route a review to "existing Luna2 / fleet_shard_2, not the
auto-creation log-tail pane", then asked for "an actual pickup/action, not publication alone".

## 1. Which pane can actually receive work

```bash
cmux list-workspaces
cmux list-pane-surfaces --workspace workspace:<w>     # surface refs + titles
ps -t ttys016 -o pid=,etime=,command= | head          # argv decides, not the title
```

Observed result that mattered: the named "auto creation" surface ran
`tail -n 40 -f /tmp/worldai-p1-drive.sHOFC8Ya/autocreation-recovery.md` — a log tail. A steered
pointer landed as an echo (`dispatch-receipts.json: status=submitted_unverified`) and nothing
executed. The real owner was a Codex subagent inside a root TUI session.

## 2. Find the parent session of a subagent lane

```bash
grep -l "fleet_shard_2" ~/.codex/sessions/2026/10/24/*.jsonl
python3 - <<'PY'
import json
for line in open('rollout-....jsonl', errors='replace'):
    if 'fleet_shard_2' in line:
        d = json.loads(line); print(d.get('timestamp'))
PY
```

Take the first rollout line's `payload.cwd` — that cwd identifies the owning workspace/surface
(`/Users/jleechan/projects/worktree_p0_2423423` → the "P0 tasks" surface). Cross-check with the
repo's own PR comments: a comment stating "`<lane>` remains sole source/lifecycle owner" is the
strongest available statement of incumbent identity.

## 3. Delivery ladder (quote all three states)

```bash
cmux agent messages status surface:1000100117          # "Messages to surface:… are on."
cmux agent message --from hermes surface:1000100117 - < brief.md
# → "Queued message 29ee7611-… for ------ P0 tasks (surface:1000100117)."
timeout 40 cmux send --surface surface:1000100117 "Read queued cmux agent message 29ee7611 …"
timeout 30 cmux send-key --surface surface:1000100117 enter
cmux agent inbox --surface surface:1000100117 --json
```

- Message states seen: `queued` (no `delivered_via`, no `read_at`) → `delivered` via
  `codex.prompt-submit` → `read_at` epoch set (e.g. `1792853007.302096` = `14:43:27Z`).
- If the pane shows the prompt still sitting in the composer (`› Read queued …`), the Enter did not
  reach a prompt: send `send-key enter` again and re-read the inbox. This happened once in-session.
- A stalled goal (`Goal stalled (/goal resume)`) does not block the drain; the queued prompt is
  what produces the `codex.prompt-submit` event.

## 4. What "pickup" looks like when it is real

The parent replied and wrote artifacts, which is the only acceptable proof:

- receipt `receipt.json` with `lane`, `status: picked_up_offline_plan_only`, `head`,
  `source_edits:false`, `tests_launched:false`, `captures_or_provider_calls:false`, `merge:false`
- a plan file whose sha256 was declared in the receipt and recomputed locally
- later: phase metas `start_utc/end_utc/epoch/exit/command/head/source_sha/test_sha/log_sha` and
  `EXIT=` lines inside the logs

## 5. Receipt path that does not exist

The lane cited `/tmp/pr277-two-answers.hvqonenn/receipt.md` with sha256 `dec2a358…`; `find /tmp -name
'*two-answer*'` returned nothing on that host. Correct handling:

- state that this specific receipt path does not exist (not "the lane lied", not "unverified claim")
- verify the fact it claimed from another retained artifact — `red-corrected.sha256` listed
  `src/services/mvpSiteClient.ts 1a61cd93…`, byte-identical to `git show HEAD:…`, which bound the
  RED phase to pristine source independently
- leave the blank `test_sha=` in that phase's `.meta` untouched and say so

## 6. Verification commands used on the returned work

```bash
ssh <host> 'cd <worktree> && git rev-parse HEAD && git diff --numstat && git diff --check'
ssh <host> 'cd <worktree> && git diff -- src/… | sha256sum'     # compare to receipt hash
shasum -a 256 <local copies>                                    # compare to receipt log_sha
gh gist view <id> -f <name> --raw | shasum -a 256               # published == local
```

All three matched the receipt (`cee2d00b…`, `3d1a59e8…`, `4c621be1…`, log `284bd1a3…`), which is
why the numbers could be republished; `git diff --numstat` also proved the test file change was
`95/0` (zero deletions ⇒ no assertion weakened).

Cross-skill detail for building such an export packet:
`devops/receipt-provenance-discipline/references/retained-original-export-ledger.md`.
