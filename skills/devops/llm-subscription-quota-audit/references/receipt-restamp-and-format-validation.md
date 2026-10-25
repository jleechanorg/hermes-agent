# Never restamp a receipt; a validator's PASS is format, not provenance

Session: PR254 harness port. Two independent provenance mistakes happened in one review, both
of which would have produced a clean-looking but false evidence chain.

## 1. The receipt that must not move

A read-only backend contract (`health`, `campaigns`, `tools_list`) was executed at
`4e2ebcba5468eb0b839a15fcc08f324829e06f93`. The PR head later advanced to
`ec4cb61d432ed1795fe6ea23c47c369f455f888f`.

The operator's instruction was exact: *"retain the prior `4e2ebcba` three-read real backend
receipt with original timestamps rather than restamping it as an `ec4` run."*

Rules that follow:
- A receipt is bound to the bytes it ran against. Copying it under a new head label is
  fabrication, even when the delta looks small (`ec4` was 8 files, +168/−23 over `4e2ebcba`).
- Preserve the original file untouched *including* its timestamps and hash; if its declared
  configuration was wrong, add a `CORRECTION.md` beside it. Do not edit the original into
  correctness — the record of what was actually declared is itself evidence.
- If a later head needs the same contract, run it again and keep two receipts. Say plainly which
  head each one covers.

## 2. Format validation passed while provenance was wrong

The contract's `load_runtime_prerequisites` gate rejected nothing in this declaration:

| field | declared | correct |
|---|---|---|
| `WORLDAI_FRONTEND_URL` | `https://mvp-site-app-dev-…run.app` (the **backend**) | the actual Expo candidate app origin |
| `WORLDAI_FRONTEND_SHA` | `4e2ebcba…` (the **test-harness** commit) | the app revision (`0c9201f9…` in that session) |
| `WORLDAI_BACKEND_SHA` | `caadac7cf8fcf59c01bf8f2396656deb98452c7c` | unchanged |

It returned PASS because both SHAs were well-formed 40-hex and both URLs were credential-free
HTTPS origins. That is all such a validator can check. Therefore:

- Never write "prereqs PASS" as if provenance were established. Write "format-valid; provenance
  binding is X" and state the binding explicitly.
- **Harness SHA and app SHA are different provenances.** A harness commit in a `FRONTEND_SHA`
  slot still passes regex validation and produces a meaningless receipt.
- The blocked receipt was still true *as a blocked receipt* (`exit 2`, zero requests sent): the
  outcome stood while the declared configuration was wrong. Keep both facts; do not discard the
  blocked record because its labels were bad.

## 3. Supersede, don't silently reuse

An earlier PR comment had recorded `4e2ebcba` as the "frozen review subject". After the head
moved, that record was stale and dangerous — a reviewer following it would read the wrong bytes.
The fix is one short supersede comment: old SHA marked historical, new SHA named, delta called
out as review-invalidating, and an explicit line that no `/advice` receipt exists at either SHA.

## Checklist

- [ ] Every receipt names its own head; no receipt is relabeled.
- [ ] Original artifacts preserved byte-for-byte (sha256 recorded before and after any copy).
- [ ] Corrections live in a sibling note, never as edits to the original.
- [ ] Validator success reported as *format* success until byte/provenance binding is shown.
- [ ] Harness revision and app revision kept in separate fields and named separately.
- [ ] Stale review-subject records superseded on the PR, not reused.
