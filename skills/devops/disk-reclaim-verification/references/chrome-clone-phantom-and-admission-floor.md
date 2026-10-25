# Case: 824 GiB clone figure, 99 % disk, and a runner floor that was not the real floor

2026-10-24. Host down to 15–19 GiB free on `/System/Volumes/Data` (98–99 %). Incoming status report
asserted: "several panes report the Data volume at 98 % and ez-gh-actions is refusing Mac runner
admission because free space is below its **30 GiB** floor — the 0-runner symptom is disk, not churn."

Everything in that sentence was partly right and partly inherited hearsay. Reconciliation below.

## 1. Where the nominal bytes were

```bash
df -g /System/Volumes/Data | tail -1     # 926  846  19  98%
du -g -d1 /private/var/folders 2>/dev/null | sort -rn | head
#   829  /private/var/folders/j0
du -g -d3 /private/var/folders/j0 2>/dev/null | sort -rn | head -3
#   824  .../X/com.google.Chrome.code_sign_clone
```

829 GiB of the 846 GiB "used" sat in `/private/var/folders/<u>/<h>/X/com.google.Chrome.code_sign_clone`
— the well-known hardlink farm (installed binary `stat -f '%i links=%l'` showed `links=587`, one link
per clone). 824 GiB of nominal `du` was therefore **not** reclaimable.

## 2. What the sanctioned cleaner actually did

```bash
cd ~/projects_other/disk_magician
DISK_MAGICIAN_AUTO_CLEAN=1 ./disk_magician.sh clean --live     # exit 0
# Cleanup Category Summary: Categories attempted: 12
#   ⚠️ 1 of 12 categories FAILED: - Codex SQLite vacuum (exit 1)
# Dirs removed: 124  Total freed: 1469140 KB  (~1434 MB)
ls -1 .../X/com.google.Chrome.code_sign_clone | wc -l          # 586 -> 13
```

570 clone directories removed, and `df` **did not move at that moment** — which is exactly the trap in
§1 of the SKILL. Do not stop the analysis there.

## 3. The release arrived late

| time (UTC) | free | note |
|---|---|---|
| 23:55 | 16 GiB | clean running, clones being removed |
| 00:06 | 15 GiB | clean finished, clone count 586 → 13 |
| 00:13 | **41 GiB** | no further deletion; APFS/purgeable release |
| 00:19–00:24 | 37–41 GiB | oscillating as Chrome respawned clones |

Growth sampled over 90 s while idle: clone dir nominal **+1.4 GB**, `~/.codex` +34 MB, `~/.hermes`
+18 MB, `df avail` −986 MB. So a single sample is meaningless in either direction.

Attempted WAL truncate at the same window did **not** contribute:

```bash
sqlite3 -cmd '.timeout 8000' ~/.hermes/state.db 'PRAGMA wal_checkpoint(TRUNCATE);'
# 1|721415|115   -> busy=1, nothing truncated; the -wal was still 2.8 GB afterwards
```

## 4. The floor was 15, not 30

```bash
grep -nE 'min_free_disk_gb' ~/.config/ezgha/config.toml
# 19:min_free_disk_gb = 15   # ... config value is now the sole floor
grep -rn '30 \* 1024' ~/ez-gh-actions-workdir/ez-gh-actions
# scripts/colima-trim-guard.sh:43: EMERGENCY_BYPASS_KIB=$((30 * 1024 * 1024))
```

The 30 GiB number was a Colima trim-guard bypass constant, not the admission gate. Satisfying it would
have meant deleting another 15 GiB of user data to clear a bar the host never had to clear.

`~/ez-gh-actions-workdir/ez-gh-actions/doctor.sh` is legacy; `scripts/runner_dashboard_host_probe.sh`
is the machine-readable admission surface:

```bash
bash scripts/runner_dashboard_host_probe.sh --host-class mac
# {"disk":{"status":"healthy"},"fleet":{"configured":4,"executing":4,"idle":0,"down":0}}
```

and the fleet itself is **org-scoped**:

```bash
gh api repos/jleechanorg/worldarchitect.ai/actions/runners --paginate   # [] — wrong scope, not zero runners
gh api orgs/jleechanorg/actions/runners --paginate -q '[.runners[]|{name,status,busy}]'
# ez-mac-runner-h-1..4 online+busy; 11 of 12 Linux online
```

## 5. The residue that needs a human decision

`growth-top10 --json` put the gap-to-floor at **+68.6 GiB since 2026-10-14**, concentrated in paths the
owner's own policy marks `never_delete`: `~/.codex/sessions` 73 GB, `~/.codex/thread_history_1.sqlite`
23.5 GB, `~/.claude/projects` 16.7 GB, `~/.hermes/state.db` 13 GB. The 23.5 GB DB had
`page_count 6006691 / freelist_count 0` — vacuum is a guaranteed no-op there, so the only lever is row
retention, i.e. an explicit user decision. Filed as `ez-gh-actions-xaa1` (unbounded, no sweeper owner)
and `jleechan-492h` (silent vacuum-category failure).

Honest close-out shape used: freed-range + admission probe + the trees that will refill the disk in
days + the one decision that is the user's. No claim that the cleanup "solved" the disk.
