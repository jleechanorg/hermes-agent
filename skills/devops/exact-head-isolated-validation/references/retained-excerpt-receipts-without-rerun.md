# Retained-excerpt receipts: publishing original RED/GREEN without rerunning

Trigger: a reviewer says *"publish the existing RED/GREEN logs, exact patch, hashes and ORIGINAL command
timestamps so this can be independently checked — do not rerun tests just for receipts"*, or
*"the posted counts alone are not independently verified yet"*.

Rerunning to produce a nicer artifact destroys the property being asked for (that the receipt reflects the
run that actually happened). Publish what you have, labelled precisely.

## 1. Say what the log is

If stdout was consumed inline (foreground run, `| tail`, `| grep`) it was never written to disk. Publish the
**retained excerpt verbatim** under a header like:

```
RETAINED EXCERPT — RED baseline at <head-sha>, unpatched
run window: <window>
invocation: <exact command>
NOTE: retained stdout excerpt as returned at run time; full log was not captured to disk
      (foreground run, tail-filtered). No rerun was performed to produce this file.
```

Do not pad it into something that looks like a complete log.

## 2. Bound the timestamp honestly

When you have no per-command clock, do not invent one. Bracket the run with durable artifacts that carry
their own time:

- **in-log timestamp** — pytest's first logging line (`2026-10-24 11:36:15,665 - root - INFO …`) is the
  strongest evidence and belongs in the header.
- **artifact mtime** — `stat -f '%Sm %N' -t '%Y-%m-%dT%H:%M:%S%z'` on the patch/build script that the run
  consumed (start bound).
- **adjacent durable record** — a bead created (or a cron job registered) immediately after the restore
  carries `created_at` / `next_run_at`; that is the end bound.

State it as a window: *"after 11:39:07 (v1 patch mtime) and before 11:40:10 (bead `rev-…` created_at right
after the restore)"*. A bounded window is checkable; a fabricated exact second is not.

## 3. Separate static from executed, per claim

Deterministic checks are legitimate receipts but are **not tests**:

| check | label |
|---|---|
| `len(file)` vs ratchet constant, `sha256`, JSON manifest parse-back | **static** |
| `git apply --check` | **applicability, zero writes** |
| pytest run | **executed** — cite counts + duration only for the artifact that ran |

If a revision was made after the executed run (wording fix, re-hash), say plainly: *"v2 has NOT been through
pytest; only v1 has the N-passed run"*, and give v2's statically verified numbers as static.

## 4. Keep the two artifacts apart

- Hash **each** patch version (`sha256` per file) and state which one the suite measured.
- For the other version, publish the exact differing lines rather than a vague "same except wording".
- Publish the **unpatched source hashes** at the head too, so the reviewer can recompute the diff and the
  resulting hashes independently.
- Also publish the tree-state invariant: `git status --porcelain` empty + `git rev-parse` = the head SHA,
  patch unapplied, no commit/push/merge, no paid replay.

## 5. Delivery surface

Textual evidence (logs, diffs, JSON) belongs in **fenced code blocks** in the message body — Slack renders
them as monospace and the reviewer can copy them out. Reserve native file upload for binary media
(screenshots, video); uploading a `.log`/`.patch` is not required and does not improve checkability.

## 6. Packet layout that reviewers accepted

```
evidence/
  01-RED-<head7>-unpatched.log        # retained excerpt + assertion body + independent numeric line
  02-GREEN-<patch>-Npassed.log        # retained excerpt + the restore block that followed it
  03-<patch-v1>.patch                 # the artifact the executed run measured
  <patch-v2>.patch                    # current recommendation (static verification only)
  05-SHA256SUMS                       # shasum -a 256 over every file above
  06-RECEIPT.md                       # timestamps table, hashes, wording rationale, static-vs-executed
```
