# Custody disposition and bead-id reconciliation

Recipes behind the "Custody reconciliation: ids and refs that don't resolve" section. All read-only.
Verified 2026-10-24 across the WorldAI / dark-factory lanes.

## 1. "Reconcile bead X with the retained owner"

Peer reports arrive as *id claims*. Two ids can both fail to resolve — the one in the report and the
one inside the peer's own proof artifact.

```bash
# per-repo first (br is repo-scoped; a miss in one repo proves nothing)
for d in <repo-a> <repo-b> <worktree-c>; do
  printf '%s: ' "$d"; (cd "$d" && br show <id> 2>&1 | head -2)
done

# then every store on every reachable host
for f in $(find ~ -maxdepth 6 -path '*/.beads/issues.jsonl'); do
  h=$(grep -oE '<id1>|<id2>' "$f" | sort -u | tr '\n' ','); [ -n "$h" ] && echo "$h $f"
done
ssh <linux-host> 'for f in $(find ~ -maxdepth 6 -path "*/.beads/issues.jsonl"); do grep -oE "<id1>|<id2>" "$f"; done'
```

Reading the result:

- **Absence is only meaningful if sibling ids resolve.** Session case: the Level worktree store held
  `rev-k3y9aq`, `rev-zfx0k`, `rev-j7zbo`, `rev-ene3xu`, `rev-5kg83j` … but neither `rev-8i6wq` (peer's
  P1 report) nor `rev-4ioks` (the id the peer's gist said it closed). That contrast is the finding;
  a bare "not found" in an unenumerated store is not.
- **Never create the bead** to make the reconciliation true — that is a writer action, and it
  fabricates the custody record the peer asked you to *find*.
- **Recover the payload from the surviving artifact.** The gist carried the four findings verbatim
  ("audit reported repaired without writing sheet mechanics", "saved sheet lost
  `resource_registry.sculpt_spells`", "reload sheet lost …", "level-up HP gains withheld"), so the
  scope survives even with no bead. Quote the artifact, not the peer's paraphrase.
- Report form: `bead <id>: not present in N stores on M hosts; proof artifact <url> retains the
  <k>-finding text; custody = <named owner or unidentified>; nothing created.`

## 2. "That commit is local-only" / "was it actually pushed?"

`git branch -r --contains <sha>` is a **remote-tracking** read and can under-report (stale fetch) or
mislead. Publication needs the live remote:

```bash
git ls-remote origin | grep <sha>            # refs/heads/… and refs/pull/<n>/head are publication
git status -sb                                # branch tracks origin/<x>, no [ahead N] ⇒ no local-only delta
git merge-base --is-ancestor <sha> origin/main  # NO ⇒ merged nowhere yet
```

Session case: peer said `3904f1b9` was "local test-only, not a verified remote push"; `ls-remote`
showed it as both `refs/heads/fix/…` and `refs/pull/9733/head`, while the worktree branch tracked
that origin branch with no ahead/behind delta. Correct the record but keep the nuance: **remote
state proven** vs **push-receipt ledger entry not checked** are different claims, and "no receipt"
must never be restated as "no push".

## 3. "Route this to the existing <lane>" — receiver check before any steer

```bash
cmux workspace list | wc -l                  # scope of the census
cmux surface list | grep -iE '<lane>|<repo>|<topic>'
grep -A14 '<surface uuid or handle>' cmux_current.json | grep -E 'kind|state|last_activity'
```

- A hit is a **receiver** only if the surface carries an agent (`"kind": "codex"|"pi"` with a
  `state`); a `"kind": "terminal", "state": "current"` row is a shell, not an inbox.
- Lane names also live in session transcripts only. `grep -rl '<lane>' ~/.codex/sessions/<date>` can
  find *discussion* of the lane; if those transcripts say `(workspace/surface unverified)`, the lane
  has no address and the answer is "receiver unidentified", not a queued steer.
- Also check the orchestration registry the lane would need: `command -v ao` on the target host.
  `ao: command not found` + an empty `~/.ao/data` means there is no AO project to address either.
- Deliverable when no receiver exists: enumeration counts + the two candidate surfaces you rejected
  and why + the single missing input (the surface ref or host+session).

## 4. "Why didn't the org-repair sweep handle PR N?" — read the dispatcher, not the summary

```bash
S=~/.local/state/<job>; ls -t $S | head        # discovery-<epoch>.tsv/.json, outcomes.jsonl, runs.jsonl
grep '"number":<N>,' $S/outcomes.jsonl | tail -3   # per-PR decision records
tail -c 1200 $S/runs.jsonl                     # run counters (dispatched/admission_deferred/fixed_confirmed)
journalctl --user -u <unit> --since '<t0>' --until '<t1>' | grep <N>
git -C <repo> show <deployed-pin>:jobs/<job>/<script>.sh | sed -n '<a>,<b>p'   # gate ORDER
```

What each leg buys:

- `outcomes.jsonl` row → `classification`, `session_action`, `result`, `verified`, `head_before →
  head_after`, and a blocker snapshot (`mergeability`, `conflicting`, `failed_checks`).
- `journalctl` → the human-readable pair that names the suppression, e.g.
  `outcome <repo>#<n> fixed_confirmed (reconciled)` then `skip <repo>#<n> (no conflict or failed check)`.
  Two lines, same second, and they beat any inference from counters.
- `git show <pin>:…` → proves which gate fired **first**. Session case: the eligibility skip
  (`mergeable != CONFLICTING && -z failures`) sat at line 333, the owner lookup
  (`pr_green_session_record`) at 425, the non-terminated-owner cap bypass at 429–434. Since 333
  `continue`s, the 30-slot cap and the owner lookup were **never evaluated** for that PR — so a peer's
  "cap is the reason" framing was wrong, and the honest answer is "the selector declined it as
  not-actionable at that run".
- Cite the run timestamp as the epoch from `runs.jsonl` (`run_ts`) plus the human UTC derived from it,
  and note when a newer discovery snapshot exists with **no** matching run record — that is
  "snapshot taken, no decision yet", not a decision.

## 5. Distinguishing published content from uncommitted content (same lane, two identities)

When a peer corrects "published head is X, repair source is DIRTY and unpublished":

```bash
git -C <wt> rev-parse HEAD            # == published head ⇒ the repair is uncommitted by definition
git -C <wt> status --porcelain        # the dirty set, quoted file by file
gh pr view <n> --json headRefOid,state
```

State the structural conclusion ("no commit above the published head, therefore the repair cannot be
published") rather than repeating the peer's sentence, and **do not** stash/commit/clean the tree —
preserving it is the whole point of the handback.
