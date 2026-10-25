# Reading a retained `/advice` primary-pair `receipt.json`

The canonical runner (`~/.claude/skills/advice/scripts/run_primary_pair.py`) leaves one
`receipt.json` per invocation in the `--output-dir` you passed. It is the cheapest
evidence of which reviewer lanes actually ran, and it costs no model call — never probe
a lane to answer a question this file already answers.

## Where to find one

```bash
ls -dt /tmp/advice-primary-pair-* /var/folders/*/*/T/advice-primary-pair-* /var/folders/*/*/T/tmp.*/results 2>/dev/null | head
```

`results/` holds `codex.txt`, `opus.txt` and `receipt.json`. A 0-byte lane file means that
lane produced no verdict, regardless of what any summary later claimed.

## Top-level keys (observed 2026-10-25, runner unchanged since 2026-10-15)

```
checkout_kind            # e.g. independent_clone_no_local
cleanup.{success,error,path}
clone_shas.{codex,opus}  # both must equal the requested ref
codex_model              # e.g. gpt-6-sol (the runner passes -m explicitly)
document_bundle_sha256   # null for revision reviews; set for --document mode
document_hashes
descendant_termination_failures
operation.{success,error}
original_changed_components
original_checkout_unchanged       # must be true
original_repository_unchanged     # must be true
overlap_proven                    # concurrency barrier held
parallel_dispatch                 # both lanes started together
review_kind                       # revision | document
reviewers.<lane>.transport        # e.g. "codex exec --yolo", "claude -p --model opus --dangerously-skip-permissions"
reviewers.<lane>.status           # success | error
reviewers.<lane>.started_ns / ended_ns
reviewers.<lane>.attempts[]
sha                               # the exact reviewed SHA
timeout_grace_seconds / timeout_seconds
```

Per attempt: `exit_code`, `failure` (`timeout`, `nonzero_exit`, `missing_verdict`, …),
`forced_pipe_close`, `stderr`, `transport`, and `descendant_*` supervision fields
(`descendants_discovered/terminated/surviving`, `descendant_termination_verified`,
`descendant_supervision_errors`).

## How to read it for a capacity report

1. `original_checkout_unchanged`, `original_repository_unchanged`, `overlap_proven` all
   true → the run is usable as evidence; any false means the verdicts may not be used as
   claimed.
2. Per lane: `status`, `attempts[].exit_code`, `attempts[].failure`, and the byte size of
   `<lane>.txt`. A lane with `exit_code: 1` + `failure: nonzero_exit` + 0-byte file
   returned **no verdict** even if the receipt itself is `success` at the operation level.
3. For a walled Codex lane, `attempts[].stderr` contains the literal provider error with
   the reset (`ERROR: You've hit your usage limit … try again at <date>`). Quote it
   verbatim and mark the timezone unknown when the provider does not state one.
4. Count votes honestly: one vote per lane that produced a `VERDICT:` line with a
   `COVERAGE:` declaration. `2+` votes → may emit `APPROVED`; exactly `1` → `WITHHELD`
   even when that vote approves.

## Worked example (2026-10-25, PR #286 review at `bab77a4e`)

- `review_kind: revision`, `parallel_dispatch: true`, `overlap_proven: true`,
  `codex_model: gpt-6-sol`, `original_checkout_unchanged: true`.
- `reviewers.codex`: `transport: codex exec --yolo`, one attempt, `exit_code: 1`,
  `failure: nonzero_exit`, `stderr` ending in
  `ERROR: You've hit your usage limit … try again at Oct 30th, 2026 7:35 PM`;
  `codex.txt` = 0 bytes.
- `reviewers.opus`: `transport: claude -p --model opus --dangerously-skip-permissions`,
  `exit_code: 0`, `opus.txt` = 2574 bytes with a full
  `VERDICT/REASONING/RISK/COVERAGE` review.
- Correct conclusion: **1 vote → `WITHHELD`**, and the same receipt simultaneously proves
  the pair mechanism works and that Codex is walled until the stated date. Do not report
  this run as an approval.
