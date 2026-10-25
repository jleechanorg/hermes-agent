# Case file — Chrome `code_sign_clone` reclaim pinned by inode matching (2026-10-24)

Repo `jleechanorg/disk_magician`. Surface `1000100000` (worktree_dropbox) in a cmux OFF-TRACK census:
"625 GiB Chrome code_sign_clone reclaim identified and still blocked; cleanup_code_sign_clones.sh
fails closed on the slow `lsof +D` probe; lane A's fix died at cap with no branch/commit/PR."

## What was actually true

| Census claim | Source of truth |
|---|---|
| "no branch/commit/PR" | worktree `~/projects_other/wt-codesign` had branch `fix/code-sign-clone-bounded-liveness` (off origin/main) **tracking origin/main**, with **451 uncommitted lines** across 3 files |
| "fails closed on the slow `lsof +D` probe" | true for the classifier — but a **second** probe in `c14_probe.py` was the real blocker |
| "625 GiB reclaim" | `du -sk` = 707,700,840 KB over 480 children; **never converted into a `df` delta** |

## Probe inventory (three layers, only the last one decides)

1. `scripts/cleanup_code_sign_clones.sh` — per-candidate `lsof +D` (lane A replaced it with one bounded
   `lsof -w -n -P -F pcn` pass + a 60 s index cache; PR #262).
2. `scripts/lib/artifact_verdict.sh` — `_av_open_file` -> `c14_probe.py open-file`.
3. `c14_probe.py open_file()` — `lsof -w -n -P -Fn -a -d '^cwd' +D <root>`; `if out: print("yes")`
   with `stderr=STDOUT`, so any diagnostic also reads as "open".

## Root cause

Every `code_sign_clone.<id>` child is a **hardlink farm** of the installed bundle:

```
$ stat -f '%i links=%l' .../code_sign_clone.KRVIDB/Google Chrome.app.bundle/Contents/MacOS/Google Chrome
2390441631 links=481
$ stat -f '%i links=%l' /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
2390441631 links=481
```

`lsof +D` matches by dev+inode, so while the browser runs, every clone answers "open". Path-based
view: `lsof -w -n -P -Fn | grep code_sign_clone/...` -> **2 of 480** genuinely open (one AsideBrowser
clone, one Chrome clone held by the headless Chrome pid).

Note the two shapes inside the tree: the 519 MB framework dylib has **distinct** inodes per clone
(`links=1`), while the Mach-O binary is the shared hardlink — so per-file `links` must be checked,
not assumed tree-wide.

## Live-run receipt (why the dry run is not evidence)

```
dry run : Dirs removed: 479  Total freed: 706398544 KB  active: 2  unverified: 0
--clean : 34x "Removing:" then "C14 kept ... (kept:open-file)"
          grep -c 'Removed (quarantined)' = 0
          ls "$TARGET" | wc -l = 480  (unchanged)
          df avail unchanged
```

Killed the run after confirming every candidate was being kept by layer 3.

## Fix delivered (PR #262, `[hermes][deepseek-4.1-flash]`)

- `run_bounded` — portable watchdog for bash 3.2 (no GNU `timeout`), rc 124 + marker file, so a
  timeout is never confused with the command's rc and partial output is never authoritative.
- `build_liveness_index` — attributes each open fd to `<name>.code_sign_clone` or
  `code_sign_clone.<id>`, drops pids that fail `ps -p`.
- `liveness_refresh_if_stale` — rebuild at most once per `CODE_SIGN_CLONE_LIVENESS_MAX_AGE_SEC`
  (60 s); lsof cost constant in candidate count.
- Fail-closed preserved as `kept:unverified:<reason>`.
- Tests: `test_cleanup_code_sign_clones.sh` (10/10, `lsof invocations: 1 for 12 clones`),
  `test_cleanup_safety.sh` (143 pass).

## Remaining fix (bead `disk_magician-eah5`)

`c14_probe.open_file` must switch to path-prefix matching over one bounded `lsof -w -n -P -Fn` pass
with a cached index (`C14_LIVENESS_MAX_AGE_SEC`, default 60), keeping `kept:check-failed` for missing
lsof/diagnostics and `deferred:tree-walk` for cap/deadline. Stubs in `tests/test_artifact_verdict.sh`,
`tests/test_c14_review_fail_closed.sh`, `tests/test_cleanup_live_semantics.sh`,
`tests/test_cleanup_code_sign_clones.sh` assume `+D` and must be updated, plus one regression test:
two dirs hardlinked to one inode, one open -> that dir `yes`, the other `no`.

## Host note

`uptime` load average was 457 during the session; `write_file` calls timed out at 420 s and every
command crawled. Check `uptime` before blaming a tool or a lane for being slow.
