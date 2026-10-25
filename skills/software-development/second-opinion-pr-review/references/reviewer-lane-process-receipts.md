# Reviewer-lane process receipts — wrapper vs child, hangs, and non-clean labelling

Verified 2026-10-25 on `jeff-ubuntu` while running A3 (`agy.real`) and C (`/secondo`) review seats
for two adapter PRs. The failure was not the model: it was my own receipt discipline.

## What happened, exactly

Lane: A3 backend addendum #2, packet 123,232 B, `agy.real --model gemini-4-argon-high
--print-timeout 540s -p "$(cat pkt.txt)"`, launched through `timeout 900 ssh …`.

Timeline (all UTC):

| time | event |
|---|---|
| 05:37:10 | lane started, `meta.txt` written with START + packet hash |
| ~05:39 | model finished emitting its full answer (12,926 B) |
| — | process **never exited**; `timeout 600` around agy did not reap it |
| 05:54:45 | I SIGKILLed the `timeout` wrapper parent |
| ~05:56:50 | orphaned `agy.real` child (PID 3755593, **PPID 1**) finally terminated after SIGTERM was ignored → SIGKILL |
| — | `pgrep -af "gemini-4-argon-high|request_second_opinion"` then returned empty |

The background hook that eventually fired reported `exit code 124` — the **wrapper's** timeout, not
the model's exit. `meta.txt` contained only START/hash lines: the post-run receipt block never ran
because the wrapper died first.

## The two claims I had to retract

1. "A3 backend: exit 0, `05:37:10→05:39:1xZ`" — false. There was no exit code at all.
2. "All reported runs are terminal" (a parent-lane assumption I repeated) — false while the orphan
   child was still alive; the correct answer required `pgrep`, not the wrapper's death.

Both were corrected by name, with the true state: **verdict text present, receipt NON-CLEAN,
wrapper killed 05:54:45Z, orphan terminated 05:56:50Z, no successful exit code.**

## Rules that now hold

- **Exit code comes from the terminal state.** Background/`wait`/`poll` result, or the script's own
  captured `$?`. Presence of output is not an exit code.
- **A killed wrapper leaves an orphan.** After any kill, prove emptiness:
  `pgrep -af "<model-binary>|request_second_opinion"`. `ps -o pid,ppid,etime,stat -p <pid>` showing
  `PPID 1` is the tell that you killed the parent only.
- **SIGTERM may be ignored.** Escalate to SIGKILL, then re-verify, and record both steps.
- **Freeze bytes across the kill.** `sha256sum` + `wc -c` before and after must agree; then the
  output is a complete stream and the verdict text stays quotable.
- **Never call a hung lane a pass *or* a failure.** The label is `NON-CLEAN RECEIPT`.
- **Do not re-dispatch to "clean up" the receipt.** Re-running is a new paid call and needs explicit
  authorization; a hung-but-complete lane is reported as-is.

## Wording for the correction (reuse verbatim)

> Packet `<sha>` (N bytes), start `<t0>`. The model emitted its full answer and then never exited.
> The bounded `timeout` wrapper did not reap it; my SIGKILL of the wrapper parent landed at `<t1>`;
> the orphaned child (PID `<pid>`, PPID 1) survived and was terminated at `<t2>`. There is **no
> successful exit code** for this lane. Output bytes are stable before and after the kills
> (`<bytes> B, sha256 <hash>`), so the verdict text is intact — it is **not** a clean terminal run.
> Unaffected: `<other lanes and their real exit codes>`.

## Adjacent lesson: authorization to publish is not authorization to publish *this*

In the same session a sanitized archive was requested for publication while a factual correction was
being reconciled. Publishing immediately (before the correction landed) produced a bundle carrying a
stale `exit 0` line, and the correction then had to be appended to the live gist. When a parent lane
says a factual reconciliation is in flight, prefer: verify → publish → **append a dated correction**
over: wait indefinitely (the parent may assume publication already happened). Both paths need the
append-only mechanics in `evidence-packet-sanitization`.
