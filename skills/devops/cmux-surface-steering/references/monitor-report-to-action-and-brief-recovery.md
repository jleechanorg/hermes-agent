# Watch report → verified action: merge-state drift, brief recovery, stand-down

Session: 2026-10-24 ~09:31–09:45Z. Trigger: a 3-part automated `cmux watch report` delivered into
Slack with no explicit ask, whose 3/3 section flagged several surfaces and said one was
"worth re-issuing to a real agent".

## 1. Reports are snapshots — reconcile against live sources before acting

The report's own cycle time was `09:29Z`. Its claims vs live reads minutes later:

| Report claim | Live read (09:36–09:41Z) | Command |
|---|---|---|
| `disk_magician` #254 "green but merge refused by base branch policy, looping 2h43m" | **MERGED** `mergedAt 09:29:56Z`, merge commit `fd96713b`, head `341ad28d` | `gh pr view 254 -R jleechanorg/disk_magician --json state,mergedAt,mergeCommit,headRefOid` |
| `ez_gh_actions` #187/#188 "draft/unmerged, one check CANCELLED" | accurate: both OPEN + `isDraft:true`, `mergeStateStatus: CLEAN`; #188 carried exactly one `CANCELLED test-on-ezgha` | `gh pr view <n> --json state,isDraft,mergeStateStatus,statusCheckRollup` |
| `EXACT_REVIEW_SHA…` PR #10528 "repair delivered, acceptance blocked" | PR itself MERGED; only real-provider acceptance outstanding | `gh pr view 10528 -R jleechanorg/worldarchitect.ai --json state` |

**Rule:** the merge state is the one field most likely to flip inside a report's window, and it is
the one that decides whether the lane still has work. Check it first; everything else in the
report is usually still true.

`gh pr diff --numstat` returned empty for the merged/limited repos in this session, so prod-vs-
non-prod deltas were reported from `--json additions,deletions` totals with an explicit
"split not computed" caveat rather than inferred.

## 2. Recovering a brief that landed in bash

Surface `surface:1000100060` (workspace `1000100020 "hermes"`, title `~/.hermes`, a **non-focused**
pane) had the whole dead brief plus the shell error in scrollback:

```bash
cmux read-screen --workspace workspace:1000100020 --surface surface:1000100060 \
  --scrollback --lines 120 | tail -80
# …
# jleechan@…:~/.hermes$ P-1 item 3 auth/cutover: you are the retained owner with no executing actor. …
# bash: P-1: command not found
# bash: report: command not found
```

Both the brief body and the failure mode are recoverable this way; the pane title alone
(`~/.hermes`) told you nothing about which brief it was.

**Then verify what work actually remains before starting a lane.** The brief referenced
"auth/cutover" + "a settings-path gap" + "a real headed run". Greps of `~/.hermes` and `~/roadmap`
for `auth/cutover`, `settings-path gap`, `P-1 item` returned **zero** hits — the context lived only
in a lane evidence file:
`/tmp/worldai_frontend/evidence/auth-cutover-headed-acceptance-plan-current.md`. That file already
contained a dated "Executing-actor assignment and current gap report" from an earlier Hermes pass,
i.e. a previous agent had already executed the deterministic half.

Sequence that worked: recover brief → find the plan/receipt in `/tmp` evidence → identify the one
story with no human prerequisite (story 1: rendered behavior of the candidate origin) → execute
that → append a dated actor+gapp section to the plan file → report. Do not open a fresh agent lane
for a brief whose remainder is human-gated (signed-in browser profile, provider console change):
it can only re-poll.

## 3. Steering a lane whose PR already merged

```bash
cmux agent message surface:1000100001 \
  "PR #254 is MERGED (mergedAt 2026-10-24T09:29:56Z, merge commit fd96713b). Your gate loop
   targets a merged PR: stop re-checking gates, confirm the merge on main, then stand down and report."
# → Queued message 955461f5-b158-447a-9a31-ce2c9ccafabe for disk (surface:1000100001)
cmux agent inbox --surface surface:1000100001
# → queued 955461f5  agent: PR #254 is MERGED …
```

Keep the stand-down to 1–3 sentences (long bodies hang the relay) and report it as
**queued, not read** until `cmux agent inbox` shows `read`.

## 4. Reconciling the report's own labels

The report names lanes as `<title>__<surface-id>` (e.g. `_hermes__1000100060`). Those are not
workspace refs: `cmux tree --all | grep -nE '<id>'` resolves them to
`surface surface:1000100060 [terminal] "~/.hermes"` under `workspace workspace:1000100020 "hermes"`,
which is what every later read/steer must use. A grep for the numeric id is the cheap identity step —
`cmux list-workspaces` titles alone will not contain `_hermes`.
