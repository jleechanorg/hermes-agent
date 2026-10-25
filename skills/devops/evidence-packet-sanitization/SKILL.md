---
name: evidence-packet-sanitization
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [evidence, provenance, redaction, manifest, review]
    related_skills: [receipt-provenance-discipline, artifact-readback-verify, evidence-attach-to-slack]
description: Sanitize or repair a published evidence packet.
---

# Evidence packet sanitization and repair

Thin entry point. The full recipe is a support file on the `receipt-provenance-discipline` skill — read it first with
`skill_view(name='receipt-provenance-discipline', file_path='references/packet-sanitization-and-derivation-repair.md')`.
The reusable redactor + manifest builder is `skill_view(name='receipt-provenance-discipline',
file_path='scripts/sanitize_packet.py')`.

## When to use

- You are about to publish BEFORE/AFTER media, receipts or logs to a public GCS prefix, gist, or PR attachment.
- A reviewer says any of: identifiers still visible, "status parsing records `->`", missing original
  build/auth/proxy records, stale index, manifest that won't verify, "sanitized derivatives, preserve originals
  privately", "explain the auth path against the non-injected-auth rule".
- A second/third review round lands on a packet you already published.

## Invariants (each one cost a review round when missed)

1. **Repair derivations, never re-run.** No new browser run, token mint, gameplay, or second operator to fix paperwork.
2. **Split directories.** `publish/` = sanitized, uploaded as-is. `private-originals/` = raw media/logs, never uploaded,
   never deleted. New prefix per revision (`…-v3`) + `SUPERSEDED.md` in the old one.
3. **Mask provenance tokens before redacting identifiers** — served bundle `index-<hash>.js`, asset fingerprints
   `Name.<hash>.ttf|webp`, full sha256, sha prefixes, `page@<hash>`. Otherwise you publish `index-campaign-E.js`.
4. **Per-file redaction policy.** Ids/slugs/titles only in records that can carry them (capture logs, transport logs, run
   output, harness source). Build/export logs get path-only redaction — they hold asset hashes, not account ids.
5. **Pixels count.** A caption burned into the video (`… | campaign <id> | <utc>`) must be re-encoded out: cover the line
   and redraw it with a stable label, regenerate stills/sheets from the derivative, then verify with `vision_analyze` plus
   an ink-run scan. Label the file a derivative and record the original's sha256.
6. **Manifest can't self-checksum; index can't hold the manifest hash.** Relative paths, no self entry, index records
   counts only. Publish the manifest sha256 out-of-band, then prove it by downloading the whole published prefix and
   running `shasum -a 256 -c SHA256SUMS.txt` there.
7. **Missing records get named, not reconstructed** (`payload_was_persisted: false`; "no SSE chunk records exist").
   A fresh recomputation may stand in for a lost binding only if it is labelled a fresh check.
8. **Asymmetry is data.** `2× 401` on one take and `0× 401` on the other (429 rate-limit answered first) must be
   reported as observed — smoothing it to "401 in both takes" is an instant reviewer catch.

## Report shape

Headline verdict (including any correction that changes their decision) → item-by-item `objection → fix` table →
full-length corrected hashes → proof commands with observed output → "still unproven, agreed" list.

## ZIP-as-transport publication (verified 2026-10-25)

A packet often arrives as a small `.zip` whose only job is transport. Publish its **members**, never
the archive, and prove the chain in this order:

1. **Identity of the transport.** `ls -l` + `shasum -a 256 <zip>` and compare against the byte count
   and hash quoted in the request. A mismatch stops the publication.
2. **Fresh task-owned extraction.** `D=$(mktemp -d …) && unzip -q <zip> -d "$D"`; never extract into a
   shared or pre-existing directory (a concurrent run deleting its own `/tmp/<name>` will delete your
   cwd mid-flight — that failure looks like `fatal: Unable to read current working directory`).
3. **Member hashes.** If the archive carries `SHA256SUMS`, run `shasum -a 256 -c`; otherwise hash each
   member directly and print `bytes + sha256 + name` as the receipt.
4. **Manifest cross-check is not a checksum of the archive.** A `manifest.json` inside the packet may
   list **repo source paths** (`AGENTS.md`, `.claude/skills/…`), not zip members. Those rows will
   "not match" any member and that is expected — verify one or two of them against the live ref
   instead (`gh api repos/<org>/<repo>/contents/<path>?ref=<sha> -H 'Accept: application/vnd.github.raw' | shasum -a 256`).
5. **Publish with the label inside the artifact.** Put the derivative/scope statement in the gist
   `--desc` as well as in the message, so the artifact is self-labelling when read later without the
   thread: which file is a redacted derivative, which are byte-identical originals, and what the
   packet does *not* claim.
6. **Preservation readback.** When the request says "preserve the older gist", prove it after
   publishing: `gh api gists/<old-id> --jq '"\(.updated_at) \(.history[0].version)"'` for every prior
   gist and quote the unchanged timestamps. A new gist never mutates an old one, but the receipt is
   what the parent lane needs.
7. **Fetchback per file via the API's own `raw_url`** (`gh api gists/<id> --jq '.files | to_entries[] | .value.raw_url'`),
   re-hash, and assert `sha256 == local` and `size == info.size` for every member before reporting
   "published".

## Append-only correction of an already-published gist (verified 2026-10-25)

A parent lane will sometimes send a scoped factual correction **after** you already published. The
rule is: preserve history, add a dated correction, never silently swap bytes.

1. **Verify the correction archive first** — byte count + sha256 against the quoted identity, fresh
   `mktemp -d` extraction, then **verify every `prior_sha256` against the bytes that are actually
   published** before replacing anything. A correction manifest that claims to replace a file whose
   prior hash you cannot confirm is a stop, not a merge. Report `prior verified N/N; new verified N/N`.
2. **`gh gist edit <id> f1 f2 …` is not a multi-file updater** — it prints its usage and does
   nothing (only `-a/--add`, `-f/--filename`, `-r/--remove` exist, and `-f` opens an editor). For a
   multi-file replacement in one call use the API:

   ```bash
   python3 - <<'PY'
   import json, pathlib
   src = pathlib.Path("/tmp/corr"); names = ["README.md", "review.md"]     # only changed files
   pathlib.Path("/tmp/patch.json").write_text(json.dumps(
       {"files": {n: {"content": (src / n).read_text()} for n in names}}))
   PY
   gh api -X PATCH gists/<id> --input /tmp/patch.json \
     --jq '"rev \(.history[0].version) revs \(.history|length) files \(.files|length)"'
   ```

   GitHub keeps prior revisions, so replacing a file's content is history-preserving; confirm the
   revision count went **up** (`revs 2 → 3`) and quote both the new revision and the retained count.
3. **Adding instead of replacing** — when the instruction is "publish a clearly dated correction; do
   not delete history", name the added file with the date and subject
   (`CORRECTION-2026-10-25T0612Z-<topic>.md`) and use `gh gist edit <id> --add <file>`. Its body must
   name the retracted claim, the true facts, and state that no model verdict changed.
4. **Post-edit readback must classify every file**, not just re-hash: label each as
   `NEW-CORRECTED` (matches the correction manifest), `ORIGINAL-KEPT` (still matches the publication
   manifest), `DATED-CORRECTION`, or `!!CHANGED` (unexpected — stop and disclose). A replacement that
   also mutates three bystander files is the failure mode this check exists to catch.
5. **Keep `--desc` and the in-file labels in sync with the correction** so a later reader who finds
   only the gist never sees the retracted claim without its correction.

## Pitfalls

- Publishing the packet before splitting raw from sanitized; later redaction then means re-uploading media.
- Writing the index before the final manifest, leaving stale `entries: N` and a dead hash.
- Describing a re-encoded derivative as the original capture.
- **Redacting payload fields but not audit principals.** GCP Monitoring objects carry the operator's address in
  `creationRecord.mutatedBy` / `mutationRecord.mutatedBy`, and channel objects carry secrets in `labels`
  (`auth_token`, `number`, `email_address`). A regex aimed only at `email_address` published a policy JSON that still
  leaked an address. Redact by key **and** by any value matching a bare-address regex, then re-fetch the served bytes and
  grep for `@gmail`, `xoxb-`, `xoxp-`, `"number": "+`.
- **Publishing before verifying the served artifact.** Create the gist/upload, then download every raw URL back,
  recompute sha256 and row counts, and compare to the retained originals. If that check fails, delete the artifact
  (`gh gist delete <id> --yes`), publish a corrected one, and disclose the superseded ID rather than silently swapping.
- Quoting only local paths plus "hash …" instead of publishing the bytes: a reviewer cannot re-verify what they cannot
  fetch. Publish exact bytes with secrets redacted, and list the unpublished exact-bytes sha256 next to the published
  derivative sha256 so the redaction delta is auditable.

