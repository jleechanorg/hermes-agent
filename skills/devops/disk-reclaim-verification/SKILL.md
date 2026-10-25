---
name: disk-reclaim-verification
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [disk, cleanup, lsof, hardlink, reclaim, fail-closed, evidence]
    related_skills: [repo-work-census, receipt-provenance-discipline, fail-closed-evidence-gates]
description: Verify a disk reclaim freed bytes; fix "in use" refusals.
---

# Disk reclaim verification — "did it actually free bytes, and why is it refusing?"

Disk-cleanup work fails in two ways that look identical in reports: the cleaner **refuses**
(fail-closed on a liveness probe) and the numbers are **apparent size**, not reclaimable bytes.
This skill is the verification ladder plus the liveness-probe forensics.

## When to Use

- A census/report says "N GiB reclaim identified and still blocked".
- A host is at ~99 % full and some consumer (runner admission, CI, build) refuses to start "because of
  disk" — verify the threshold, the reclaimable bytes, and the consumer's own admission surface.
- `--clean` runs but `df` does not move, or a cleaner logs `kept:open-file` / `kept:unverified`.
- A cleanup PR claims freed space.
- A safety gate keeps candidates because "a file is open".

## 1. Never quote `du` as reclaim

`du` sums allocated blocks per path. It **over-reports** across APFS clone/hardlink farms and says
nothing about what `df` will show after a delete.

```bash
df -k /System/Volumes/Data | tail -1        # macOS: the DATA volume, not /
df -k <path> | tail -1                       # Linux target volume
du -sk <tree>                                # apparent/allocated — a HYPOTHESIS, not a receipt
```

- macOS `df -h /` is the **sealed system snapshot**; the number that matters is
  `/System/Volumes/Data`. Quoting `/` makes a 94 %-full disk look 20 % full.
- Reclaim = `df avail` delta across a **real** delete. One candidate deleted and measured beats a
  whole `du` table. If you cannot delete one (§4), say "unmeasured" instead of quoting `du`.

Controlled rebuttal you can re-run in about a minute on APFS — `cp -c` a 300 MB source into two clones:
`du` totals 921,600 KB (3 × 307,200) and `df` drops only ~300 MB; deleting **both clones** returns
`du` to 307,200 KB ("600 MB freed") while `df avail` recovers ~2 MB. Three copies cost one copy
physically. This reproduces the production shape (73 clones, `du` 104.1 GiB, `df` 8.2 → 8.5 GiB) and is
the cheapest way to prove a "huge reclaim" figure is phantom.

Dry-run output is a **prediction**: `Dirs removed: 479  Total freed: 706398544 KB` means the
classifier *would* remove 479 entries. The receipt is:

```bash
grep -c 'Removed (quarantined)' clean.log     # 0 == nothing was actually removed
ls "$TARGET" | wc -l                          # before/after count must differ
```

Verified 2026-10-24: a dry run predicted 479 removals / 706 GB; the live `--clean` logged
`Removing:` for ~34 candidates, the quarantine gate kept every one, `grep -c 'Removed (quarantined)'`
= **0**, the child count stayed **480**, and `df avail` never moved. Both figures in the report were
predictions.

## 2. Enumerate EVERY liveness probe in the deletion path

A cleaner usually has more than one. Fixing the first one changes nothing if a shared safety gate
still answers.

```bash
grep -n 'lsof' scripts/cleanup_<target>.sh scripts/lib/*.sh scripts/*probe*.py
grep -rn 'kept:open-file\|open-file\|+D' scripts/ | head -20
```

Typical stack (disk_magician):

| Layer | Owner | Predicate |
|---|---|---|
| candidate classifier | `scripts/cleanup_<x>.sh` | own lsof pass -> ACTIVE / INACTIVE / unverified |
| shared verdict | `scripts/lib/artifact_verdict.sh` | leases, live cwd, **open file**, secrets, mtime |
| actual removal | `quarantine_remove` / C14 gate + `scripts/c14_probe.py` | **its own** bounded probe |

The last layer decides. Trace `c14_remove` -> `quarantine_remove` -> `c14_probe.py <subcommand>`
before claiming a reclaim is unblocked.

## 3. `lsof +D` matches dev+inode — hardlink farms read "all in use"

`lsof +D <dir>` resolves open files by **device+inode**, not by path string. macOS app
`code_sign_clone` trees are hardlink farms to the installed bundle, so while the app runs **every**
clone reports open:

```bash
stat -f '%i links=%l %N' "<clone>/<App>/Contents/MacOS/<App>" "/Applications/<App>.app/Contents/MacOS/<App>"
# inode 2390441631 links=481 ... identical in all 480 children and in /Applications
```

Path-based matching gives the truth in one bounded pass:

```bash
lsof -w -n -P -Fn 2>/dev/null | sed -n 's/^n//p' \
  | grep -o '<scan-root>/[^ ]*code_sign_clone/code_sign_clone\.[A-Za-z0-9]*' | sort -u | wc -l
# 2 of 480 — the rest are hardlink siblings, not live handles
```

Rules:

- Deleting a **hardlink name** cannot decide anything about the running process (it holds the inode),
  so inode matching over-preserves — but **path matching is not the authority either**: `lsof`'s `n`
  record for a hardlink-shared vnode names whichever link is cached, so one path match can be a sibling
  alias and the truly-holding clone may not be reported at all. Treat the path view as a *lower bound*
  (2 of 480 is "at least 2"), never as the classifier.

  The authority is a two-rule stack:
  1. **Per-clone evidence** — a clone is active only when a reported open file is *exclusive*
     (`nlink <= 1`), is not a regular file, is already unlinked but still open, **or** the reporting
     pid's launch path (`ps -p <pid> -o comm=`) lies inside that clone (`/var` and `/private/var`
     spellings are the same path).
  2. **Launch-time keep-set** — when the only evidence is a hardlink-shared inode, preserve every clone
     created at or after the **oldest live holder's** start time (`ps -p <pid> -o lstart=`, trim
     trailing spaces before `date -j -f`). A clone that predates every live holder cannot belong to one.
     Unreadable start times or mtimes keep (fail closed).
- Index-building traps that silently re-open the hole: keep **all** holders per directory (a
  `!seen[$1]++` one-PID-per-dir index drops concurrent holders); an uninspectable pid is **unknown, not
  dead** (`ps`/`kill -0` both failing ≠ "gone"); and never swallow a diagnostics-read failure with
  `|| true` — an empty diagnostics string must still mean fail-closed, not "clean pass".
- Per-pid probing is cheap, global snapshots are not: `ps -p <pid> -o comm=` ≈ 11 ms while
  `ps -Ao comm=` took **2 m 15 s** on a 2,071-process host and once added ~3 min to every suite run.
  Ask per pid, never take a global snapshot per candidate.
- Keep fail-closed but distinguish three answers: `open` (path match), `no` (clean complete stream),
  `unverified`/`deferred` (lsof missing, cap/deadline hit, any diagnostic). "Unverifiable" must never
  be reported as "in use" — they need different fixes.
- `stderr=STDOUT` + `if output: print("yes")` is a false-positive generator: one `lsof: WARNING`
  becomes "open". Classify on record lines (`^n`); handle diagnostics as a separate fail-closed cause.
- Stale pids must not mask eligibility: verify with `ps -p <pid>` (sees other users' processes)
  before believing a holder; fall back to `kill -0` only when `ps` is unavailable.

## 4. Destructive-command routing

`rm -rf` outside cwd, and `rm -rf` with a shell-variable target, are refused by the CC safety net.
That refusal is a routing signal, not a wall: use the repo's own gated cleaner so the delete is
quarantined, identity-checked and logged. When the **gate itself** is the false positive (§3), fix the
gate in its own PR and then run the cleaner — do not hand-`rm` the tree, and do not report "blocked"
while the sanctioned route is still broken.

## 5. One fix per PR, gates in the PR body

- Each liveness fix is its own independent PR (classifier, then gate) — never one integration PR.
- Green gates != merge authority: report `Evidence Gate pass` / `Test and lint pass` / `MERGEABLE` and
  leave the merge to the orchestrator.
- disk_magician's Evidence Gate wants an exact `## Evidence` section with bold fields
  `Claim class` / `Verdict` / `Commands and results` / `What this proves` / `What this does not prove`;
  `production` additionally needs a gist URL + the full lowercase head SHA. Claim class `tooling` +
  `Verdict: PARTIAL` is the honest shape when tests pass but live reclaim is unmeasured.
  Validator path + failure text: `references/disk-magician-evidence-gate.md`.
- State the unproven half explicitly ("does not prove that `--clean` frees bytes: the C14 gate still
  keeps every clone").

## 6. Case file

Full transcript of the 480-clone / 675 GiB Chrome `code_sign_clone` block, including the classifier
fix (single bounded `lsof -w -n -P -F pcn` pass + index cache) and the remaining gate fix:
`references/code-sign-clone-hardlink-inode.md`.

A second production pass (586 clones, `du` 824 GiB, host at 99 %) is written up with the deferred-release
measurements and the runner-admission end-state proof in
`references/chrome-clone-phantom-and-admission-floor.md`.

A third pass — an **active** leak (157 clones, 221 GiB, newest one minute old, disk falling during the
diagnosis), with the full three-lane reconciliation, the empty-snapshot negative and the load
attribution: `references/code-sign-clone-active-leak-case.md`.

## 7. Verify the claimed floor before spending reclaim budget on it

A status report usually carries the threshold it wants satisfied ("runners refuse admission below
30 GiB"). That number is a **claim**, not a config read. Grep the live owner first:

```bash
grep -nE 'min_free_disk_gb' ~/.config/ezgha/config.toml     # -> 15, not 30
grep -rn '30 \* 1024' ~/ez-gh-actions-workdir/ez-gh-actions  # -> only EMERGENCY_BYPASS_KIB in colima-trim-guard.sh
```

Verified 2026-10-24: the inherited report asserted a 30 GiB runner floor; the real admission floor was
`min_free_disk_gb = 15` and the only 30 GiB constant in the repo was a Colima trim bypass. Chasing the
wrong number wastes the entire reclaim budget and makes a healthy host look blocked. Quote both values
in the report — the claim and the live config — and reconcile them explicitly instead of silently
adopting either.

## 8. Release can be deferred — sample `df` over minutes, not seconds

`df avail` does not always move at the instant the names disappear: APFS extents of a deleted
clone/hardlink farm can be released asynchronously, and macOS may also drain **purgeable** space once
free space crosses its own low-water mark. Measured 2026-10-24:

- 586 → 13 clone dirs deleted (live `--clean`, `Dirs removed: 124`, exit 0) with `df` still at 15 GiB.
- ~7 minutes later `df` went **15 → 41 GiB free** with no further deletion.
- The same tree then regrew ~1.4 GB nominal per 90 s while Chrome respawned clones, so free space
  oscillated 37–41 GiB.

Rules: take **≥5 samples over several minutes** before declaring either success or failure; report the
range (`free oscillated 37–41 GiB`), not one lucky sample; and never attribute the whole delta to the
cleanup when purgeable release is a live alternative — say what was measured and what is merely
temporally adjacent.

## 9. SQLite candidates: check the freelist before promising a vacuum

```bash
sqlite3 <db> 'PRAGMA page_count; PRAGMA freelist_count; PRAGMA page_size;'
# 6006691 | 0 | 4096  -> 24.6 GB, zero free pages: incremental vacuum reclaims NOTHING
sqlite3 -cmd '.timeout 8000' <db> 'PRAGMA wal_checkpoint(TRUNCATE);'
# 1|721415|115        -> busy=1: it did NOT truncate; re-`ls -lh` the -wal before claiming a win
```

`freelist_count = 0` on a huge DB is the tell that the only lever left is **row retention** (a
destructive user decision), not vacuum. A routine cleaner reporting `Codex SQLite vacuum (exit 1)` is
that same category failing closed — say so instead of counting it as freed.

## 10. End-state proof for a reclaim that exists to unblock admission

Space freed is the intermediate metric; the receipt is the consumer's own admission surface.

```bash
bash scripts/runner_dashboard_host_probe.sh --host-class mac
# {"disk":{"status":"healthy"},"fleet":{"configured":4,"executing":4,"idle":0,"down":0}}
gh api orgs/<org>/actions/runners --paginate -q '[.runners[]|{name,status,busy}]'
```

A repo-scoped `repos/<owner>/<repo>/actions/runners` returning `[]` is **not** "no runners" — the fleet
is org-scoped. Confirm scope before reporting zero.

## 11. Stale pile vs ACTIVE leak — decide with the newest mtime, then the rate

A 200 GiB clone tree can be a fossil or a running faucet; the fix and the urgency differ completely.
One read answers it:

```bash
C="$TMPDIR/../X/com.google.Chrome.code_sign_clone"     # note: X, NOT T
ls -1 "$C" | wc -l                                      # 157 entries
ls -lt "$C" | head -3                                   # newest mtime: 21:22 — one minute ago = LIVE
du -sxh "$C"                                             # 221G total (~1.4G per entry)
find "$C" -maxdepth 1 -mindepth 1 -type d -mmin -30 | wc -l   # 3 young, 155 older than 30m
df -h /System/Volumes/Data | tail -1                     # 31Gi avail, falling while you diagnose
```

- **Newest mtime within minutes ⇒ active leak.** Say "still leaking, N GiB and falling" and treat the
  reclaim as urgent-but-regenerable; a pile whose newest entry is days old is a one-off cleanup.
- Split the inventory by age before proposing a delete: `-mmin +30` is the safe batch, `-mmin -30` keeps
  whatever the running app is verifying right now. Quote both counts.
- Measure the rate, not just the size: two `df` samples minutes apart while the tree grows give
  "~1.4 GB per Chrome launch". That number is what tells the operator how long the host has.

Two path traps make naive scripts silently scan nothing or refuse to run — both hit in one session:

1. `$(getconf DARWIN_USER_TEMP_DIR)` / `$TMPDIR` returns `.../gn/T`. The clone trees live in the
   **sibling `X/` directory** (`.../gn/X/<bundle-id>.code_sign_clone/code_sign_clone.XXXXXX`). A cleaner
   that walks `$TMPDIR` reports 0 candidates while 221 GiB sits next door.
2. `getconf` returns `/var/folders/...` (a symlink), so a guard written as
   `case "$ROOT" in /private/var/folders/*/T)` rejects the real path: `unexpected temp root`. Resolve
   first (`ROOT_RESOLVED="$(cd -P "$ROOT" && pwd -P)"`) and validate the resolved path.

Ready-to-run, dry-run-by-default guard for exactly this tree:
`scripts/reclaim_code_sign_clones.sh` (`--delete`, `--min-age-min`, validates temp root, only touches
`code_sign_clone.*` children). Dry run verified 2026-10-24: `155 dirs, 218.2 GiB` reclaimable, 14 s.

Root-cause direction: the clones are Gatekeeper verification copies left behind when a launch fails to
finish (headless Chrome killed mid-launch). A min-age purge stops the bleeding; the durable fix belongs
in whatever launches/kills the browser, not in the cleaner.

## Pitfalls

- Scanning only `$TMPDIR`/`T` for `code_sign_clone` trees and reporting "nothing to reclaim" — they live
  in the sibling `X/` dir (§11).
- Treating a `code_sign_clone` pile as stale without checking the **newest** entry's mtime; an active
  leak refills faster than a one-shot cleanup (§11).
- Reporting a lane "blocked on a slow `lsof`" when the actual refusal came from the **quarantine gate**.
- Accepting a pasted `du`/dry-run figure as the reclaim value; both are hypotheses.
- Measuring `df -h /` on macOS (sealed volume) instead of `/System/Volumes/Data`.
- Killing a long `--clean` run without first checking `grep -c 'Removed'` — if it is 0, the run is
  diagnostic noise, not a partial success.
- Declaring success from `tests pass`: tests prove the classifier, not the deletion.
- Concluding "the fix did not work" from a still-unchanged `du` while the delete never happened;
  verify the delete first (§1 receipt), then the space.
- A `du` figure that exceeds what `df` says is used is arithmetically impossible for real data —
  that gap is the tell that the tree is hardlink/clone-shared and the "reclaim" figure is inflated.
- Concluding "the delete freed nothing" from a `df` read taken seconds after it. Release is deferred
  (§8): sample over minutes, and re-check whether the consumer keeps recreating the same tree.
- Taking the threshold in the report as the threshold to satisfy. Read it from the live config owner
  (§7); a stated "30 GiB floor" was actually `min_free_disk_gb = 15`.
- Promising vacuum savings without `PRAGMA freelist_count` — `0` free pages means vacuum is a no-op
  and only row retention can help (§9).
- macOS BSD `du` rejects `-s` together with `-d` (`du -sg -d2 <dir>` prints nothing) **and** buffers
  output until exit, so a `timeout`-killed `du` yields an empty result that reads like "no data".
  Use `du -g -d1` (no `-s`) or redirect to a file and read it after.
- Reporting a repo-level runners API `[]` as "no runners" when the fleet is org-scoped (§10).
