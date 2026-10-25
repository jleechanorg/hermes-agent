# Answering a reviewer's provenance asks from the RETAINED ORIGINALS (verified 2026-10-24)

Trigger: an independent reviewer posts a packet review whose "smallest next action" is
*"export a sanitized ledger from the already retained original run; mark absent data
unavailable; preserve exit code and every failed assertion; no rerun, no assertion
weakening, no source takeover."* The temptation is to re-run the capture (forbidden) or to
answer from the published reduction (insufficient). Answer from the originals.

## 0. Locate the run directory, not the reduction

The published artifact is a **sanitized reduction** (gist with 9–10 files). The originals
sit in the run output dir on the capture host (`/tmp/<topic>-<sha>.<rand>/` — grep
`ssh <host> 'ls -lt /tmp | grep <topic>'`). Hash the originals you cite:

```bash
ssh <host> 'cd /tmp/<run-dir> && sha256sum acceptance.json boundaries.sanitized.json \
  network.sanitized.json cdp-stream.sanitized.json dom-progress.json prelaunch.json'
```

The ledger's authority comes from those hashes, not from the gist's checksum list.

## 1. Absolute capture time is usually still in the original

Reductions drop wall-clock; harnesses keep an epoch dict (`timings_epoch_seconds`,
`started`, `reload_started`). Convert with
`datetime.fromtimestamp(v, datetime.UTC)` and **prove the epoch is real UTC**, not a
run-relative offset, by matching one epoch against an ISO-stamped row in a different
file (`network.sanitized.json` row epoch `1792849805.1369126` ⇄
`2026-10-24T13:50:05.136913Z`). Only then state the capture window.

Then say plainly: report creation time ≠ capture time. Reviewers check this.

## 2. "Prefix only" in the reduction ≠ the original lacks full hashes

Published timelines showed `a00b8b831a263612` (16 hex). The original receipt carried the
full `a00b8b831a26361225b1374e…1bd1ce9` for returned / every read / rendered. Export the
full values, and state the basis honestly: *string equality over values the driver
recorded from API responses and the DOM, not an independent re-download of the stored
object.*

## 3. Distinguish a cardinality-induced failure from a real mismatch

Contracts of the shape

```python
selected = rows[0] if len(rows) == 1 else None        # L20 / L29
a_matches  = bool(returned and selected == returned)  # L30
b_matches  = bool(rendered and selected == rendered)  # L31
exactly_one = len(rows) == 1 and selected is not None # L38
```

turn **every downstream equality into False when N > 1**, even though all fingerprints
agree. Cite the contract file's own sha256 + exact line numbers, name the failure
`cardinality`, and preserve the `== 1` contract whenever the request says "do not change
exactly-one to >= 1". Never descope it as flaky; never green it by relaxing it.

## 4. Recompute BOTH named driver hashes; a third copy may match neither

Receipts name two artifacts (`driver_sha256`, `canonical_driver_sha256`) at two paths.
Recompute each from its declared path. In this session a third copy on the same host
(`/tmp/stream_avatar_acceptance.py`, `790413fd…`) matched **neither** receipt — it must be
named and excluded, or a future reader will diff the wrong pair. Then produce the delta:
`wc -lc`, `diff -u`, hunk count, `+/-` counts, and a one-bullet summary per changed
behaviour (function added, selector changed, counters added, receipt fields added).

Also flag labeling inconsistencies between the published excerpt and the source receipt
(one called the isolated run path "canonical" while the receipt named `/var/tmp/...` as
canonical). Correct the label, keep both hashes.

## 5. The unavailable table is the deliverable, not a failure

For each datum the reviewer asked for, either export it or state **unavailable** with the
code line that proves it was never recorded. Typical: query strings used only for role
classification, request ids for non-stream calls, CDP `initiator`, lifecycle
owner/generation, cache hit/consume, raw bodies, raw token/claim values (only booleans
stored). Finish with a source-candidate map (file:line) and the sentence *"candidates do
not establish ownership"* — attribution stays unproved rather than inferred.

## 6. Publication shape

- unlisted gist: `ledger.md` + `extracted-timings.json` (machine-checkable numbers) +
  `driver-delta-*.diff` + `SHA256SUMS.txt`; readback `gh gist view <id> -f <file> --raw |
  sha256sum` against the declared hash and `gh api gists/<id> --jq .public` = false.
- PR comment with `**Evidence**: <gist url>` in the first lines, headed by the unchanged
  head SHA, with an explicit closing line: *no capture, no provider call, no assertion
  edit, no source edit, no merge; the incumbent retains source ownership.*
- Run the outbound secret gate on every file and on the comment body before publishing.

## Pitfalls

- Never rebuild the numbers by hand from the reviewer's prose — recompute and print them
  from JSON; reviewers re-derive and a transcription slip costs the whole ledger.
- Epoch floats are exact to the millisecond; do not round to whole seconds and do not
  subtract across clock domains (host vs browser) without saying which clock each value is.
- If a request start and its response are matched only by arithmetic
  (`response − duration_ms/1000`), say so; response order can differ from start order.
