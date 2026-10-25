# Exporting a ledger from already-retained originals (no rerun)

Use when a reviewer asks you to "export what was already recorded" — capture UTC, request
cardinality, fingerprints, driver delta, runtime/auth provenance — and a rerun is explicitly
out of scope. Validated 2026-10-24 on a PR 277 provenance export + two peer re-reviews.

## 1. Epoch fields beat "we did not publish capture time"

A sanitized reduction often drops wall-clock while the retained original still has it.
Look for absolute epoch maps (`timings_epoch_seconds`, CDP `wallTime`) and convert:

```python
datetime.datetime.fromtimestamp(t, datetime.UTC).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
```

Then cross-check one epoch against an event the reduction *did* publish (same event, ISO form).
That converts "capture UTC missing" into a sourced value; keep the reviewer's distinction intact:
report creation time / gist publication time ≠ capture time.

## 2. Absence claims must be time-scoped, never "none anywhere"

Wrong: "no media artifacts exist under `/tmp/<pr>*`". It was checkable and false — 7 files
existed, all predating the window. Correct shape:

> All seven media files matching `/tmp/<pr>*` predate this window (newest `12:31Z`); none were
> created between `15:47Z` and `15:56Z` while the run executed.

Always `find … -printf '%TY-%Tm-%Td %TH:%TM | %s | %p\n'` and quote the newest timestamp instead
of asserting global absence.

## 3. Diff deltas: `grep -c '^+'` counts headers

`diff -u` adds `---`/`+++` lines. A header-inclusive count reports `+69/-8` when the real content
is `+68/-7`. Count with the header excluded, and state which convention you used:

```bash
grep -c '^+[^+]' d.diff   # added content
grep -c '^-[^-]' d.diff   # removed content
```

For a git worktree, prefer `git diff --numstat` — per-file `added  deleted`, immune to the problem,
and it also proves "test file N/0" (zero deletions ⇒ no assertion removed or relaxed).

## 4. Multi-copy artifact identity: hash at the receipt-declared path

Three files had the same basename and three different hashes: canonical `1154addd…` (417 lines),
run driver `f1a3dc3c…` (478 lines), and a loose third copy `790413fd…` (476 lines) that matched
neither receipt. Citing a line number without naming *which copy* produced a wrong citation
(`L466` was the run copy, not canonical `L405`).

Rules:
- Resolve each declared hash to its **declared path** and recompute there; a basename in `/tmp` is
  not the canonical file.
- Line citations carry the file identity: `canonical (417 lines, 1154addd…) L405` vs `run (478 lines,
  f1a3dc3c…) L466`.
- If a loose copy matches no receipt hash, say so explicitly so nobody cites it as either artifact.

## 5. Two vocabularies: unavailable vs unprovided

- **Unavailable / not captured** — the harness never recorded the field (query string, request IDs
  for non-stream calls, CDP `initiator`, owner/generation, cache hit). Not recoverable without a
  rerun; say "unavailable, not inferred" and give the source-candidate map without claiming a caller.
- **Unprovided** — the file exists but was not in the packet (complete drivers, auth helper,
  runtime binding). Publishing it closes the gap; absence in the reduction never proves absence in
  the world. Never upgrade either one to "disproven".

## 6. Revise a published packet append-only

- Keep revision 1 byte-identical; add `…-v2-….md` plus a `SHA256SUMS-v2.txt`, and state in the
  revision header what it supersedes (path + hash) and what changed.
- `gh gist edit <id> --add a --add b` silently added only one file. The reliable multi-file path is
  one PATCH:

```bash
python3 - <<'PY'
import json
files = ["a.md", "b.diff", "c.log"]
json.dump({"files": {f: {"content": open(f).read()} for f in files}}, open("patch.json", "w"))
PY
gh api -X PATCH gists/<id> --input patch.json --jq '.files|keys'
```

- Verify every add by fetching it back and re-hashing: `gh gist view <id> -f <name> --raw | sha256sum`
  must equal the local hash. Large text logs survive unchanged (~1.3 MB verified byte-identical).
- Correction comments name the three fixes, the new hash, and that v1 stays unmodified; do not
  silently rewrite history the reviewer already reviewed.

## 7. Deliverable shape that survived review

A peer re-review accepted this structure: capture UTC table → cardinality evidence table → code
citation for the assertion cascade → full-hash three-way equality → driver delta with both hashes
and the exact `diff -u` counts → present-vs-unavailable table → preservation/non-claims → original
artifact hashes. Every number recomputed from the originals in the same pass that wrote the file.
