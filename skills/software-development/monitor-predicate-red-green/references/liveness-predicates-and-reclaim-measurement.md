# Liveness predicates and reclaim measurement (deletion-safety gates)

Use when a cleanup/reclaim/GC gate decides "is this path in use?" and either
(a) reports everything ACTIVE so nothing is ever removed, or (b) reports a
candidate idle when a holder exists. Verified on macOS 2026-10-24 against a
Chrome `code_sign_clone` tree (480 children, ~1.4 GB each).

## The four predicate bugs, each seen live

### 1. `lsof +D` matches by dev+inode, so hardlinked trees are un-attributable

Chromium hard-links the app's main executable into **every** `code_sign_clone.*`
child **and** `/Applications`:

```
stat -f '%i links=%l' <clone>/.../MacOS/Google Chrome
→ inode 2390441631 links=481      # identical in all 480 children + /Applications
```

Consequences measured directly:

- `lsof -Fpcn +D <one clone>` reports the same pid for **every** clone while the
  app runs → the sweep classified 480/480 candidates as ACTIVE and reclaimed 0.
- A *path-prefix* rewrite does **not** fix it either: `lsof`'s `n` record for a
  hardlink-shared vnode names whichever link is cached, so the path can belong to
  a sibling clone the process never launched from.

What actually works (from the sibling PR's findings file):

1. **Per-clone evidence** — active only when a reported open file is exclusive
   (`nlink <= 1`), is not a regular file, or the reporting pid's launch path
   (`ps -p <pid> -o comm=`) is inside *that* clone (`/var` and `/private/var`
   are the same path — normalize both).
2. **Launch-time keep-set** — when the only evidence is a shared inode, keep
   every clone whose creation time is at or after the **oldest live holder's**
   `ps -p <pid> -o lstart=`. Chromium makes one clone per launch; a clone older
   than every live holder cannot belong to one. Unreadable start times/mtimes
   fail closed.
3. Keep **all** holders. An index built as `awk '!seen[$1]++'` (one row per dir)
   silently drops a second holder and turns a live tree idle.

### 2. Swallowing a diagnostics read turns the pass authoritative (fail-open)

```bash
diagnostics=$(tr '\n' ';' <"$err" 2>/dev/null || true)   # BUG
[[ -n "$diagnostics" ]] || accepted_as_authoritative     # empty ⇒ "clean"
```

An unreadable/raced stderr file yields `""`, which reads as "no diagnostics", so a
timeout or permission failure is accepted as a complete scan. Preserve unreadable
diagnostics as a distinct `kept:unverified:…` state; never `|| true` on the read.

### 3. `unknown` must not collapse into either verdict

```bash
pid_alive() { ps -p "$1" >/dev/null 2>&1 || kill -0 "$1" 2>/dev/null; }   # BUG
```

Both failing returns "gone" for a pid that is *absent* **and** for one that is
merely uninspectable (permissions, `ps` failure, pid reuse race). Three states,
not two: `live` / `proven-absent` / `unknown(fail-closed)`. Fixtures must include a
known-nonexistent pid *and* an uninspectable one; a fixture with only the former
proves nothing about the latter.

### 4. A bounded single pass is the right shape, but prove the bound

One `lsof -w -n -P -F pcn` enumeration per scan window (filtered afterward) beats
one `lsof +D` per candidate — per-dir tree walks cost seconds each and, with 400+
candidates, always time out and fail closed.

- Stock macOS bash 3.2 has no GNU `timeout`: use a watchdog subshell that kills
  with SIGTERM then SIGKILL and leaves a **marker file**, so "we timed out" is
  rc 124 and never confusable with the command's own status.
- Partial output must never be authoritative: a timeout discards the record stream.
- Cache the enumeration for a bounded age (`*_LIVENESS_MAX_AGE_SEC`, default ~60 s,
  `0` = no reuse) so cost is flat in candidate count; re-check inside that window
  immediately before each destructive removal.
- A test titled "one pass" that asserts `CALLS -gt 3` fails is not a bound proof.
  Assert the exact normal path (1 call), the exact fallback path (2 calls), and
  partial-output rejection separately.

## Reclaim measurement: `du` logical bytes are not freed space

`du` counts every clone's blocks; APFS/`cp -c` clones share extents, so deleting a
clone returns ~nothing. Controlled experiment (sibling lane, same host):

| step | `du` total | `df` avail |
|---|---|---|
| 300 MB source + 2 clones | 921,600 KB (3 × 307,200) | −300.8 MB vs before |
| delete both clones | 307,200 KB (`du` says 600 MB freed) | **−2,088 KB (noise)** |

Rules that follow:

- Only `df` (before/after, same mount) is a reclaim claim. Never report summed
  `du` output as "freed"; never label a classifier total `Total freed`.
- `rm -rf` on a computed/parent path is blocked by the safety shims anyway; the
  sanctioned removal route is the tool's own quarantine/rename + purge, which is
  also what lets a re-verify gate re-check handles.
- When a gate is deliberate fail-closed and measured reclaim is ~0, the correct
  outcome is "leave the gate alone and label the bucket non-reclaimable", not
  "relax two destructive gates to win zero bytes".

## Cheap `lsof` attribution probe (read-only)

```bash
# 1. how many candidates actually hold a path (not an inode)?
lsof -w -n -P -Fn 2>/dev/null | sed -n 's#^n##p' \
  | grep -o '<root>/[^/]*code_sign_clone/code_sign_clone\.[A-Za-z0-9]*' | sort -u | wc -l
# 2. is the "open" file shared or exclusive?
stat -f '%i links=%l %N' '<the reported path>'
# 3. where was the holder launched from?
ps -p <pid> -o pid,etime,command | cut -c1-160
```

Compare (1) against the per-dir `+D` result before believing either. On the live
host: `+D` said "open" for ~all 480 clones; (1) said 2.

## Performance traps

- `ps -Ao comm=` took 2m15s with ~2,000 processes on this host; `ps -p <pid> -o comm=`
  is ~11 ms. Never take a global snapshot per candidate.
- `ps -p <pid> -o lstart=` has trailing spaces — trim before `date -j -f`.
- GNU `stat -f %l` is *filesystem* format (max name length), not a link count; branch
  on `uname -s` before using it for `nlink`.
- "Recent activity" gates that read **content** mtimes need fixtures aged with
  `find … -exec touch -t`, not just a directory mtime.
