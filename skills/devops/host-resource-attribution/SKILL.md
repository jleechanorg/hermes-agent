---
name: host-resource-attribution
description: Read-only host snapshot — what is actually loading this box.
version: 1
author: hermes-curator
license: MIT
metadata:
  hermes:
    tags: [host, cpu, memory, load-average, processes, read-only, diagnostics]
    related_skills: [hermes-health-check, disk-reclaim-verification, read-only-diagnostic]
---

# Host resource attribution

Use when someone asks **"what is overloading this machine?"**, "is it CPU or memory?", "which process
is eating the box?", or when a lane is stalled on a "host saturated" claim. The deliverable is one
timestamped read-only snapshot plus an explicit boundary between *current consumers* and *cause of an
earlier spike*.

Nothing here mutates: no kill, no renice, no restart, no test/build launch, no settings change.

## When to Use

- "What is overloading my Mac/host?", "why is load so high?", "is it CPU or memory?"
- A lane is stalled or deferred on an "environmental / host saturated" claim and someone wants the real
  constraint named.
- Newer host figures from a peer supersede yours and you owe an honest current reading.
- You need per-process attribution (PID, executable, cwd) without reading argv or touching anything.

## 1. One snapshot, all fields, one timestamp

```bash
echo "UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"; hostname; uname -mrs; uptime
sysctl -n hw.ncpu hw.memsize
sysctl -n vm.swapusage                       # macOS: total / used / free swap
sysctl -n kern.memorystatus_vm_pressure_level # 1 normal · 2 warning · 4 critical
vm_stat | head -8                            # page size matters: 16384 bytes on Apple silicon
top -l 2 -n 0 -s 2 -o cpu | grep -E 'CPU usage|Load Avg|PhysMem' | tail -3
```

- **Take the second `top` sample.** The first sample's CPU line is cumulative since boot and will
  report nonsense on a long-uptime box; the delta sample is the real instant reading.
- Convert pages to bytes with the page size `vm_stat` prints; free pages × 16 KB is what "available"
  usually means, and `free + speculative + inactive` is the honest reclaimable estimate.
- Linux equivalents: `free -m`, `cat /proc/pressure/{cpu,memory,io}`, `vmstat 1 3`, `nproc`,
  and `df -k` on the **data** volume.

## 2. Top consumers — executable and cwd, never argv

```bash
ps -A -o pid=,%cpu=,rss=,comm= -r | head -12      # top CPU, exe path only
ps -A -o pid=,rss=,%cpu=,comm= -m | head -8       # top RSS
ps -p <pid>,<pid> -o pid=,etime=,time=,%cpu=,rss=,comm=   # cumulative CPU vs elapsed
lsof -p <pid> -a -d cwd -Fn | grep '^n'           # working directory = the only task attribution
```

- **`comm` (executable path), not `command`.** Full argv routinely carries tokens, emails, user-data
  dirs and personal paths; a diagnostic snapshot must not reproduce them.
- **Cumulative `time=` is a lifetime total, not a time series.** `441:46` of CPU over a 22 h process is
  "a standing consumer (~⅓ core continuously)", never proof it caused a spike three hours ago.
- **cwd is attribution only when it resolves to a known worktree/repo.** A cwd of `/` (or `<deleted>`)
  means **unproven task** — say "unproven", not a guessed label.
- A process name alone (`python3.14`, `gitleaks`, `bash`) is an executable, not a task.

## 3. Load average is not CPU utilization

Load average counts **runnable + uninterruptible** threads, exponentially decayed over 1/5/15 min.
On a 14-CPU box a load of 150 with **43 % idle** is normal when the host is memory-constrained:
65 login sessions and several agent runtimes leave many I/O-blocked threads, and compression/swap
stalls count as runnable while consuming almost no CPU.

So never translate "load is high" into "CPU is overloaded". Report the three separately:
**CPU idle % · memory pressure/swap · load averages**, and name which one is binding. In the
2026-10-24 case the binding constraint was memory (22 GB compressor, 14.65/15.36 GB swap, pressure
level 2), not CPU.

## 4. Current consumers vs the earlier spike — keep them apart

macOS keeps no per-process time series. Therefore:

- The snapshot table is **now**. It cannot explain a load window from an hour ago.
- Cumulative CPU, "top consumer of the day", and a peer's remembered culprit are all *unproven cause*.
- Say literally: "current consumers are X; the earlier spike's cause is unproven by me", and name what
  would be needed (a sampler running during the event) if anyone asks for more.
- When a peer publishes fresher figures (e.g. "45.89 % idle / 11.49 GiB available at 17:01"), mark your
  older numbers **historical by name** instead of re-arguing them.

## 5. Companion reads that settle the obvious follow-ups

```bash
df -h /System/Volumes/Data | tail -1        # macOS: / is the sealed snapshot; Data holds the usage
ps -p <pid> >/dev/null && echo alive || echo gone   # ps -p sees other users' processes
vm_stat | head -3                            # free/inactive/speculative pages
```

- `df -h /` on macOS makes a 94 %-full disk look 20 % full — always quote `/System/Volumes/Data`.
- `pgrep -fc <pat>` returning 0 is a known false negative under load; verify with `ps -p <pid>` plus
  the artifact mtime.
- If the ask is "what's overloading this box" and you find a reclaim story underneath, that is
  `disk-reclaim-verification` territory — do not mix apparent sizes into the host report.

## 6. Count process *states*, and hunt duplicate daemons

A load number with no state count is unattributable. Two cheap reads turn "load 236" into a cause:

```bash
ps -Ao stat | grep -c '^R'      # 263 runnable threads -> the load is real contention
ps -Ao stat | grep -c '^U'      # uninterruptible (I/O-wait) count
ps -Ao comm | sort | uniq -c | sort -rn | head -12   # count per executable
ps -Ao pid,ppid,etime,args | grep '[l]imactl' | head  # shape of the duplicate set
```

What the counts say (2026-10-24, same host as §3, later window):

| Count | Meaning |
|---|---|
| `135 com.apple.WebKit.WebContent` | browser/renderer fan-out |
| `100 limactl usernet`, **PPID 1**, up 1d09h | accumulation bug, not a workload |
| `68 login` + `68 -/bin/bash` + `43 bash` | one login shell per terminal surface (cmux panes) |
| `263` in `R` state | the load is genuine ready-queue contention |

- **Duplicate = same executable + overlapping argv identity (same pidfile/socket/subnet) + PPID 1.** That
  combination means every restart orphaned the previous daemon; the orphan set grows monotonically and
  each copy still holds RSS. Call it an accumulation bug and say so — `pgrep -c` alone will not show it.
- Compare the *shape* of argv when detecting duplicates (pidfile path, port, socket), then **do not paste
  token-bearing argv into the report** (§2). Quote the identifier (pidfile, port), not the whole line.
- Special-case the platform's own scanners: a pegged `StorageManagement`/`fseventsd` is usually the OS
  indexing or a Settings pane scanning storage, and it inflates load while the real problem is elsewhere.
- Killing duplicates is a **process-kill**, i.e. a destructive action with its own authorization. Keep it
  as a separate ask from an unrelated delete/reclaim ask; never bundle them into one approval.

## Pitfalls

- Reporting `top -l 1` CPU as the current reading (since-boot average).
- Quoting argv in a snapshot and leaking secrets/personal content.
- Naming a culprit from a process name or a lifetime CPU total.
- Reporting a load average without the `R`/`U` state counts — an unattributable number invites the wrong fix.
- Counting processes per executable and stopping there: 100 copies of one daemon with PPID 1 and the same
  pidfile is an orphan accumulation, not a workload (§6).
- Recommending a kill/renice in a read-only ask — report, don't remediate.
- Re-posting the same numbers on a follow-up: if nothing new changed, say nothing new.
