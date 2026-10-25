---
name: llm-payload-ablation
version: 1.0.0
author: hermes-curator
license: MIT
description: "Use when an LLM behavior claim needs real-API measurement."
tags: [ablation, llm, real-api, measurement, payload-replay, a/b, prompt-hypothesis, gemini]
related_skills:
  - wa-bq-forensics-read
  - wa-prompt-engineering
  - regression-test-proof-validity
  - fail-closed-evidence-gates
metadata:
  hermes:
    category: workflow
    tags: [ablation, llm, real-api, measurement, payload-replay, a/b, prompt-hypothesis, gemini]
    related_skills:
      - wa-bq-forensics-read
      - wa-prompt-engineering
      - regression-test-proof-validity
      - fail-closed-evidence-gates
last_verified: 2026-10-23
---

# LLM payload ablation — measure the behavior claim, one variable per arm

Owns the *execution* side of "is this prompt element actually causing the model's
behavior?". A code reading is a hypothesis; a single clean run is not a fix; a
string-presence test is not a behavior test. This skill replays the **real captured
payload** through the **real provider** with a **verbatim control arm first**.

The generic procedure and the stats floor also live in `~/.claude/skills/ablation`
(user-owned — read it for theory, do not edit it). This skill owns the mechanics that
actually fail in practice: payload recovery, byte-parity edits, provider replay,
scoring drift, and what to do with a null result.

## When to use

- Root cause is disputed, or two lanes disagree ("is it the banner / the state / the wording?").
- A fix is about to be written from a code reading, and the claim is stochastic.
- A PR or issue proposes a prompt edit as the *cause* of a model behavior.
- Someone reports "remove X and it stopped" at N=1.

## When NOT to use

- Deterministic bug with a unit test → write the test, not an ablation.
- A read-only forensics handoff → that is `wa-bq-forensics-read`; replay is a run, not a read.
- You do not have the captured payload and cannot get it → say so; a reconstruction is not a specimen.

## Procedure

### 1. Recover the specimen and hash-bind it

Pull the exact request from the provider-forensics table (WA: `llm_forensics.llm_payloads`).
Bind by **content**, and cite three hashes:

- `sha256(body bytes)` recomputed locally == `extra_json.request_json_source_sha256`
- `sha256(systemInstruction text)` — matches whatever the evidence owner published
- the request id (`extra_json.request_id`), which lives in `extra_json`, not a column

Both a full payload row and a stub row can exist for one turn, so select by
`LENGTH(request_json)` and a narrow `ingested_at` window rather than by `turn_index`.

### 2. Instrument = the captured body, POSTed verbatim

The strongest instrument is the captured `generateContent` body itself with the same
model, `tools`, `safetySettings`, `generationConfig` and seed-override text. Nothing
re-assembled, so there is no production wrapper to hold constant across arms — state
that explicitly in the report.

```python
urllib.request.Request(url, data=body,
    headers={"Content-Type": "application/json", "x-goog-api-key": key})
```

Do not substitute an SDK you configured yourself; that is a different instrument.

### 3. Control arm first, N≥5 — and re-score it before trusting the batch

A control that reproduces the production artifact exactly (same die, same total, same
`dc_reasoning`) is your instrument validation. If it does not reproduce, stop.

### 4. One variable per arm, byte-parity before firing

Same-offset, same-length replacement beats deletion (deletion shifts every downstream
offset and confounds content with position). Every transform must **assert** its own
effect and its byte delta before any API call:

```python
assert "TARGET" not in new_text
assert len(new_text.encode()) == len(old_text.encode())   # no volume confound
```

Byte parity matters when the edit swaps unicode (a `🚨` is 4 bytes, 1 char): pad with
spaces to reconcile bytes, not characters. Record the residual delta when parity is
impossible (a few bytes out of ~1 MB is acceptable *only* if stated).

### 5. Score mechanically over the whole raw blob

Field names drift: the same provider returns `executableCode` live and
`executable_code` in a stored capture, and final-JSON fields are often absent from the
raw response entirely. Regex the serialized response, never one field:

```python
rolled = bool(re.search(r"randint\(\s*1\s*,\s*20\s*\)", blob) or "1d20" in blob)
```

Read secondary numbers from the **code-execution result** part, not the first regex hit
in the blob — the generated code contains both branches of an if/else, so a naive
`social_hp_damage` match returns the 0 from the failure branch.

### 6. Report ratios against the control, name what N cannot show

`X/N vs control's Y/N`, the base rate, and the delta. With a 100% control base rate,
5/5 in a treatment means "not a sufficient fix", not "proven zero effect".

### 7. Decide what the null result licenses

- Every arm rolled → the behavior is **over-determined**; no single-site edit is defensible.
- A null result at the decision layer means **do not ship the prompt patch**. A contract
  test that asserts the new sentence exists would pass while behavior is unchanged —
  that is the "prompt-substring assertion" anti-pattern.
- Name the next discriminating arm instead of banking an untested gap.

### 8. Do not fabricate /rg RED from a prompt string

`/rg` requires a fresh failing **behavioral** test the fix flips. If the ablation refutes
every prompt fix, the correct ending is: report the measurement, recommend a product-level
fix, ship a bead — not a green-looking string assertion.

## Pitfalls

1. **Silent no-op edit.** The banner may be in the dynamic tail (`contents`) rather than
   `systemInstruction`, and may be double-escaped so `text.index("╔")` raises. Locate by
   an ASCII sentence inside the block, and assert the target is gone afterwards.
2. **Scoring drift.** A scorer keyed on `executable_code` scored a real roll as
   `rolled=False` on the first control. Rescore from the stored raw responses before any
   analysis; keep raw JSON per run so scoring is re-runnable.
3. **Truncated CSV reads.** `bq --format=csv` rows can exceed Python's default 131072-char
   csv field limit (`_csv.Error: field larger than field limit`). Call
   `csv.field_size_limit(64 * 1024 * 1024)` before `DictReader`.
4. **`bq` import shadowing.** Run from a neutral cwd with `PYTHONPATH` unset
   (`cd / && unset PYTHONPATH && bq …`), or a repo-root `utils.py` shadows bq's `utils`.
5. **Equal `ingested_at` filters.** Timestamps carry sub-second precision; use a half-open
   `BETWEEN` window, never `=`.
6. **Deletion confound.** An arm that removes a pre-existing sentence while adding a new
   one changed two variables; that arm is weaker evidence than the clean replacement at the
   same site.
7. **Volume confound.** Compare against the untouched baseline, not only arm-vs-arm.
8. **Field-scoped or literal-only scoring.** The model paraphrases; count semantic
   recurrences, and search the whole response.
9. **Claiming a fix from one seed.** A seed-fixed payload can reproduce byte-identically;
   that raises the base rate but proves nothing about causality.

## Reporting shape

```
## Ablation summary
- Specimen: request id, body sha256, served-system sha256, how bound by content
- Instrument: captured body POSTed verbatim; transformations constant across arms
- Control (A): X/N rolled -> base rate R%
- Arm N: <one-variable change, byte delta> -> X/N
- Verdict: <hypothesis> CONFIRMED | REFUTED-AS-SUFFICIENT | INCONCLUSIVE
- Not established: what this N cannot show
- Next experiment: the discriminating arm still unrun
```

## Support files

- `scripts/replay_ablation.py` — parameterized runner: verbatim control, transform hooks
  that must self-assert, per-run JSONL (arm, run, duration, model, provider, body sha256,
  full raw response), blob-wide scorer.
- `references/2026-10-23-wa-scene579-social-check-roll.md` — worked case: 26 real Gemini
  calls, five arms, every prompt-side hypothesis refuted including "clear the stale
  challenge state", plus the escaped-unicode banner side finding.
