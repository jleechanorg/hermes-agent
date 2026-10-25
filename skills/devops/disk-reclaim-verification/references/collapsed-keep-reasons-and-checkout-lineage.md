# Collapsed keep-reasons, retention-floor conflicts, and checkout lineage

Session evidence: 2026-10-24, disk_magician bead `disk_magician-273z`
("cleanup_pr_scratch: 'rm failed' on 35 plain user-owned /tmp files, so the 12h sweep reclaims 0").

## 1. The reported failure was fiction

Reported: `cleanup_pr_scratch.sh --clean --min-age-hours 12` →
`Dirs removed: 0  Files removed: 0  Total freed: 0 KB  Skipped (rm failed): 35`.

Reality: **no `rm` ever ran**. `scripts/cleanup_pr_scratch.sh` calls
`DM_DELETION_LOGGED=1 c14_remove "$item" --kind ephemeral`
→ `quarantine_remove` in `scripts/lib/quarantine.sh`, which prints a verdict
(`removed:<id>` / `kept:<why>` / `deferred:<why>`) and returns rc 1 for anything
that is not `removed:*`. `c14_remove` maps rc 1 to `return 1`, and the caller
prints one generic string: `echo "SKIP (rm failed): $item"` + `RM_FAILED++`.

So every **policy keep** is reported as an **execution failure**. The operator
reads "rm failed", concludes permissions/ownership, and never checks the verdict.

Diagnostic tell: `which -a rm` shows the guard shim, a manual `rm -f <same file>`
succeeds (rc 0), and the file is gone — yet the sweep "fails" on the same path.
When manual removal works and the cleaner says "rm failed", the string is a
collapse, not an errno.

## 2. Probe the verdict primitive directly — never the whole `--clean`

```bash
cd <c14-checkout>            # e.g. ~/projects_other/worktree_dropbox
printf 'a\n' > /private/tmp/pr90001-probe-14h.json
printf 'b\n' > /private/tmp/pr90002-probe-50h.json
touch -t $(date -v-14H +%Y%m%d%H%M) /private/tmp/pr90001-probe-14h.json
touch -t $(date -v-50H +%Y%m%d%H%M) /private/tmp/pr90002-probe-50h.json

bash -c 'source scripts/safety_lib.sh; source scripts/lib/quarantine.sh;
         quarantine_remove /private/tmp/pr90001-probe-14h.json --kind ephemeral'
# -> kept:recent-activity          (file survives)
bash -c 'source scripts/safety_lib.sh; source scripts/lib/quarantine.sh;
         quarantine_remove /private/tmp/pr90002-probe-50h.json --kind ephemeral'
# -> removed:3ee54712ea49fd61      (file gone)
```

Two aged copies separate "policy keeps it" from "removal is broken" in one call.
Lower-level steps when the verdict is opaque:
`python3 scripts/quarantine_rename.py bind <path> <binding>` → `candidate` →
`artifact_removal_verdict <path> --inventory-out <inv> ...` → `remove`.

Nested paths behave differently: `/private/tmp/<dir>/pr*.txt` answers
`kept:unproven-content`, because `c14_ephemeral_retention()` matches the name
pattern against the path **relative to a scratch root with no slash**.
`dmprobe/prPROBE.txt` therefore never matches `^(pr[0-9]|pr-|pr_|claude-|claude_)`.

## 3. The retention dial is not the retention floor

`c14_ephemeral_retention()` in `scripts/lib/artifact_verdict.sh` returns a hard
per-pattern floor: **2880 min (48 h)** for `pr*` / `claude*` top-level names in
scratch roots, 240 min for git-bearing dirs, 60 min for some CLI validation dirs.
`--min-age-hours 12` / `DISK_MAGICIAN_PR_SCRATCH_MIN_AGE_HOURS` only controls the
script's **pre-filter**; C14 re-checks its own floor at delete time and keeps.
Nothing between 12 h and 48 h is reclaimable, and the run reports the refusals as
rm failures.

Consequence for reporting: default sweeps agree (48 h vs 48 h) and log
`Skipped (rm failed): 0`, so the defect is invisible unless someone dials the
window down. Production evidence:
`~/Library/Logs/disk-magician-main-sweeper.log` →
`cleanup_pr_scratch.sh starting (roots: /private/tmp … , min-age: 48h)` with
`Files removed: 0` on each ~70-min run.

Fix shape (no floor loosening — C14 floors are a safety spec needing sign-off):
surface the real verdict per item, split `RM_FAILED` (genuine rm/permission) from
`C14_KEPT` with a per-reason breakdown, and log one warning when requested
retention is below the per-pattern floor.

## 4. Lineage: reproducing on the wrong checkout gives the wrong answer

Three copies of `cleanup_pr_scratch.sh` existed with genuinely different code:

| Copy | Shape |
|---|---|
| `~/projects_other/disk_magician` | older, plain `rm -f` / `rm -rf`, **no C14 libs** |
| `~/projects_other/worktree_dropbox` | newer, `c14_remove` + `scratch_lock` + `quarantine.sh` |
| `~/.local/share/uv/tools/disk-magician/.../scripts/` | deployed copy — **carries the C14 code** (lines 499/549) |

The bug did not reproduce on the older copy because there was no verdict layer —
and running `--clean` there **deleted 32 files + 6 dirs (~49 MB)** of >12 h
`pr-*` scratch in `/private/tmp` with no C14 gate. That is a real safety bypass,
not a repro. Before reproducing any cleaner defect: `diff`/`git ls-tree` the
candidates, `ls scripts/lib/`, and identify which copy the scheduler runs
(`plutil -p ~/Library/LaunchAgents/*.plist`, `~/.local/bin/diskm`). Dry-run and
primitive probes are safe on any copy; `--clean` is only safe on the canonical one.

Deploy corollary: a repo-only PR does not change live behaviour when launchd runs
the installed uv-tool payload — the promotion step must be named in the PR.

## 5. Shared scratch flock: check holders, not PIDs in a report

Stale-PID claim in the same report ("paused `cleanup_tmp` PID 67912 still holding
the scratch flock") was false: `ps -p 67912` → no row. The lock was genuinely
contended, by live runs:

```bash
lsof ~/.disk_magician_locks/scratch_cleanup.lock          # fd 4u holders
python3 scripts/scratch_lock.py run --caller probe --script x --args -- /usr/bin/true
# -> "[probe] skipped, scratch lock held after waiting 20s"   (EX_TEMPFAIL 75)
```

`scratch_lock_acquire` execs the caller under `python3 scratch_lock.py run …`, so
`cleanup_pr_scratch --clean` **skips its whole pass** whenever a long
`cleanup_tmp --clean` holds the shared flock. A sweeper that "runs" on schedule
can therefore reclaim nothing without ever appearing as a failure. Always report
lock contention separately from candidate ineligibility.
