# disk_magician Evidence Gate — required PR body shape

`pull_request_target` workflow `.github/workflows/evidence-gate.yml` checks out the **base** branch and
runs `.github/scripts/validate_evidence.py` against `pull_request.body`. It fails the PR, not CI
compile, so a green `Test and lint` does not save it.

## Hard schema

An exact `## Evidence` heading (case-insensitive match on the literal line), then these bold fields,
each on its own line:

```
**Claim class:** tooling | documentation-only | production
**Verdict:** PASS | PARTIAL | INSUFFICIENT | FAIL
**Commands and results:** ...
**What this proves:** ...
**What this does not prove:** ...
```

- `INSUFFICIENT` / `FAIL` always fail the gate.
- `production` requires `Verdict: PASS` **and** `**Evidence URL:** https://gist.github.com/<owner>/<16+ hex>`
  **and** `**Evidence SHA:** <40 lowercase hex>` equal to the PR head SHA the workflow trusts.
- Placeholders (`n/a`, `none`, `tbd`, `todo`, `trust me`, empty) are rejected; a `<!-- ... -->` in a
  value is rejected; duplicate fields are rejected.
- Section scanning stops at the next line starting with `## `, so the fields must live inside
  `## Evidence` itself.

## Observed failure text

```
Evidence Gate: FAIL: missing evidence field(s): Claim class, Verdict, Commands and results,
What this proves, What this does not prove
```

Re-running the gate: editing the PR body re-triggers `pull_request_target` on `edited`
(`gh pr edit <n> --body-file <file>`), no push needed.

## Choosing Claim class / Verdict for cleanup work

- `tooling` — scripts, cleaners, safety gates. No gist required.
- `Verdict: PASS` only when the claimed behavior was executed and observed.
- `Verdict: PARTIAL` when tests pass but the live effect is unmeasured (e.g. the classifier works but
  the quarantine gate still refuses, so freed bytes are unknown). Put that limitation in
  **What this does not prove** in one concrete sentence naming the still-blocking layer.
