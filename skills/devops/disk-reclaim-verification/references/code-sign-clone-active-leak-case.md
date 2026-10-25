# Case: an ACTIVE code_sign_clone leak on a thrashing host (2026-10-24, 21:10–21:35 PDT)

Host state when the report arrived: peer status packet claimed "26 GiB free (98 % used), load avg 411,
62 users, runner fleet admission-paused by its own 30 GiB disk floor; nothing redriveable."

## Verified live state (this pass)

```
df -h /  /System/Volumes/Data
  /dev/disk3s1s1  926Gi  13Gi  32Gi  29%  /            <- sealed snapshot, NOT the number that matters
  /dev/disk3s5    926Gi 840Gi  32Gi  97%  /System/Volumes/Data
uptime            load averages: 236.80 267.51 375.13, 63 users
ps -Ao pid | wc -l                1466
ps -Ao stat | grep -c '^R'         263   <- load is real contention, not a stale average
```

So the packet's numbers were directionally right and already drifting (26 → 32 GiB "free" on two
different measurement bases); the load had come down from 411 to 236 at read time. Quote your own sample
with a timestamp instead of adopting the report's.

## Lane 1 — top-down reconciliation, ≥5 GiB granularity

```
du -x -g -d1 /System/Volumes/Data | sort -rn | head
1032  /System/Volumes/Data          (du total)
 680  .../Users
 273  .../private
  29  .../Applications
  27  .../System
  18  .../opt
   7  .../Library
   1  .../usr  .../home

diskutil apfs list | grep -i 'Capacity In Use'
  Capacity In Use By Volumes: 960.1 GB (96.5% used)   vs 901.5 GB on the Data volume alone
```

The 1032 GiB `du` total against 901.5 GB APFS-consumed is the hardlink/clone tell, not a contradiction
(§1 of the skill). The residual is clone accounting plus one 13.7 GB sealed system snapshot.

Drill-down that found the faucet:

```
du -x -g -d2 /System/Volumes/Data/private
  238  private/var
  231  private/var/folders   <- 89 % of /private
   37  private/tmp
du -x -g -d4 /System/Volumes/Data/private/var/folders
  221  .../j0/byd1z6px.../X/com.google.Chrome.code_sign_clone
    7  .../T
    2  .../X/at.studio.AsideBrowser.code_sign_clone
```

157 entries, 1.4 GiB each, **newest created one minute before the check** — headless Chrome
(`--headless=new --remote-debugging-port=9333 --user-data-dir=~/.hermes/...`) leaking one Gatekeeper
verification copy per launch. Safe batch: 155 dirs older than 30 min = **218.2 GiB**.

## Lane 2 — snapshot deltas (coverage-validated negative)

```
tmutil listlocalsnapshots /        -> "Snapshots for disk /:" and nothing else
diskutil apfs list                 -> 901.5 / 10.9 / 1.5 / 13.7 GB volumes, no pending snapshots
```

Local TM snapshots were **not** a contributor. An empty listing is a real answer; record it so the
reclaim budget is not spent there.

## Lane 3 — outliers, and the load attribution

Runnable-state attribution mattered more than the load number:

```
ps -Ao pcpu,rss,args -r | head
  183% 1.0 GB  npm ci
  109%        fseventsd
  118% + 45%  StorageManagement extension / StorageManagementService (macOS storage scan)
  56%         cmux
ps -Ao comm | sort | uniq -c | sort -rn
  135 com.apple.WebKit.WebContent
  100 /Users/jleechan/.local/bin/limactl          <- all `limactl usernet`, PPID 1, up 1d09h
   68 /usr/bin/login  68 -/bin/bash  43 /bin/bash   (one shell per cmux surface)
```

The 100 `limactl usernet` processes were an accumulation bug: every copy carried the **same
`-p .../usernet_user-v2.pid` and socket paths**, i.e. every colima restart left the previous usernet
daemon orphaned at PPID 1 (~1.1 GB RSS total). Killing them is a process-kill (needs its own
authorization), and it is separate from the disk ask — do not bundle unrelated destructive actions.

## What the reply did

One concrete destructive authorization request plus the exact verified command, no menu:

```
bash ~/.hermes/scripts/reclaim_code_sign_clones.sh --delete     # 155 dirs / 218.2 GiB, dry-run shown
```

Items that could not be verified were reported as unverifiable rather than echoed: the packet's
"PR #251 / `codex-monitor-config` / `worktree_dropbox`" had no local worktree, no matching branch in any
local repo, and no such open PR under `jleechanorg` or `Agnt-F` — so nothing was driven.

## Transferable checklist

1. `df /System/Volumes/Data` + `uptime` + `ps ... | grep -c '^R'` — own sample, timestamped.
2. `du -x -g -d1` top-down, reconcile against `diskutil apfs list` capacity, name the residual.
3. `tmutil listlocalsnapshots /` — prove or exclude the snapshot lane in one command.
4. Drill `private/var/folders/**/X/*.code_sign_clone` and read the **newest mtime** (stale pile vs leak).
5. Attribute load to state counts and top CPU, not the load number alone.
6. Report bytes + rate + one authorization ask; keep process-kill asks separate from delete asks.
