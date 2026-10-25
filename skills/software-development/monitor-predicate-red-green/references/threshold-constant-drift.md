# Threshold constant drift — when a guard's limit outlives its policy

A guard (watchdog, time-box checker, rate/budget cap, slot limiter) usually hardcodes its
threshold as a fallback constant while citing a policy that owns the real number. When the
policy moves, the constant does not, and the guard starts enforcing a rule nobody wrote —
a **false-RED** that kills or pauses legitimate work.

Worked case (verified 2026-10-24): `~/.claude/scripts/check_autonomy_time_box.sh` defaulted
`MAX_AUTONOMY_SECONDS` to `10800` (3 h) and its header cited a `~/.claude/CLAUDE.md`
"max 3 hours" section that no longer existed. The live policy owner,
`~/.codex/AGENTS.md` § *Autonomy time-box*, says `28,800` s (8 h), renewed by each new live
human message. Effect: a flow started 4 h earlier was classified `TIME-BOX EXCEEDED`, so
autonomous lanes were paused/killed at 3 h and read downstream as "stalled".

## 1. Find every copy before touching one

The constant lives in the repo source, the installed user-scope copy, and every host that
runs the same script. All three must be enumerated, or "fixed" means "fixed on the machine
you happened to open":

```bash
grep -rn "MAX_AUTONOMY_SECONDS\|<CONST_NAME>" \
  ~/.claude/scripts ~/projects/<skills-repo>/.claude ~/.hermes/scripts 2>/dev/null
ssh -o ConnectTimeout=8 <other-host> \
  'grep -n "<CONST_NAME>" ~/.claude/scripts/<script>.sh; md5sum ~/.claude/scripts/<script>.sh'
md5 -q <copyA> <copyB>     # byte-identical today does not mean identical tomorrow
```

Record the md5 per host in the report. A drifted set is the norm, not the exception, and the
receipt is what proves which host still enforces the old number.

## 2. Confirm the policy owner by reading it, not by assuming the citation

The header's citation is the most likely thing to be stale. Grep the candidate owners and
quote the live line:

```bash
grep -nE "time-box|10800|28800|[0-9]+ hour" ~/.codex/AGENTS.md ~/.claude/CLAUDE.md
```

If the section the header names is gone (`grep` returns 0 hits in that file), the constant is
orphaned — say so in the commit message instead of quietly changing the number.

## 3. Fix shape: constant + citation + failure text, no logic change

Keep the diff to the value and the prose that describes it. Rewriting the predicate while
changing the threshold makes the RED/GREEN unattributable, and a monitor repair must stay
minimal (see the parent skill's constraints 1–2).

## 4. Prove baseline-vs-head with fixtures, not with today's ambient state

Fetch the pre-fix script from the base ref so the RED is real:

```bash
git show origin/main:.claude/scripts/<script>.sh > /tmp/proof/old.sh
```

**One fixture dir per case.** A shared `RUNTIME_DIR` contaminated the first attempt: the
"4 h-old flow" case also contained the 9 h-old fixture and reported `exit 1` for a threshold
it actually passed. Isolate:

| Case | Fixture | Baseline (3 h) | Head (8 h) |
|---|---|---|---|
| 4 h-old flow | `<dir>/old4h/flow4h.started_at` = now−14400 | exit 1, `max=10800s` | exit 0, `within 28800s budget` |
| 9 h-old flow | `<dir>/new9h/flow9h.started_at` = now−32400 | — | exit 1, `max=28800s` |

Keep the **9 h still-fails** row. A change that only ever turns red→green proves the guard
was weakened, not retuned; the row that must stay red is the evidence the cap still exists.

## 5. Harness-mechanics traps hit while writing this proof

- **The command safety net rejects computed paths.** `rm -rf "$W"` is blocked
  (`rm.recursive-force-dynamic-target`) and so is running a script through a variable
  (`RUNTIME_DIR=… bash $W/old.sh` → `analysis.dynamic-shell-source`). Write the proof to a
  **literal** path (`write_file /tmp/<name>-proof.sh`) and invoke `bash /tmp/<name>-proof.sh`;
  use `mktemp -d` for data dirs and never delete them with a swept variable.
- Keep fixture timestamps computed inside the script (`now=$(date +%s)`), so the proof is
  re-runnable instead of pinned to a wall-clock value.
- `bash -n <script>` plus one all-clear run and one exceed run is the minimum behavioural
  receipt; paste the raw lines, not a summary of them.

## 6. Deployment order — the constant is not fixed until every host is

1. Open the PR against the **repo** copy (repo copy lands through review, never direct).
2. Do **not** hand-edit the installed/remote copies first; that is exactly the
   "agents run an unreviewed variant" drift the repo rule exists to prevent.
3. After merge, re-fetch the merged file (`git show origin/main:<path>`) onto each host, then
   re-run the md5 comparison and quote all digests in the report.
4. Until then, report the defect as **still live on N hosts, fix awaiting merge** — never as
   fixed because the PR is open.

## 7. Don't fold adjacent gaps into the same PR

While proving the fix, a second defect usually appears (here: the policy documents
`--flow <id>` but the script parses no arguments, so a scoped check reports every flow).
File it (`br create`, with the file:line provenance and the PR that discovered it) and leave
it out of the threshold PR — one behaviour per PR keeps the RED/GREEN table honest.
