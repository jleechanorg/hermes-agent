# Packet sanitization and derivation repair

Use when a **already-published** evidence packet (GCS prefix, PR attachment bundle, gist) is challenged by a reviewer:
identifiers still visible, numbers that don't parse, missing originals, stale index, manifest that can't verify — or
when a packet is about to be published publicly at all.

Core rule: **repair derivations from the originals; never re-run the capture to fix paperwork.** No new browser run, no
token mint, no gameplay, no second operator. If a record never existed on disk, say so — do not reconstruct it.

## 1. Two directories, from the first publish onward

```
<state>/<topic>-evidence-<date>/
  publish/            # sanitized, authoritative, uploaded as-is
  private-originals/  # raw MP4s, stills, sheets, capture/proxy logs — never uploaded, never deleted
```

Reviewers ask for "sanitized derivatives, preserve originals privately without destructive deletion" — this layout is
that request, pre-answered. Record each original's sha256 in the receipt (`video.original_sha256`) and in the index, so
the published derivative stays traceable to the raw file. Publish to a **new** prefix (`…-v3`) rather than overwriting;
put a `SUPERSEDED.md` in the old prefix naming each defect. Overwriting published evidence destroys the audit trail;
deleting needs the user's call, not yours.

## 2. Mask provenance tokens BEFORE redacting identifiers

Naive id regexes eat the provenance you are trying to publish. Real damage seen in one pass:

| Token | Regex that ate it | Consequence |
|---|---|---|
| `index-9089102a…bb96c.js` (bundle) | `\b[0-9a-f]{24,32}\b` | published log read `index-campaign-E.js` — bundle binding destroyed |
| `Geist-Regular.5d43871….ttf`, `twin_dragon.21b9483….webp` | same | ten phantom "campaigns"; transport record falsified |
| 32-hex webpack asset hashes in build logs | same | build record corrupted |

Correct order: **mask → redact → unmask.** Protect at minimum:

```python
PROTECT = [
    re.compile(r"\.[0-9a-f]{32}\.[a-z0-9]{2,5}\b"),   # fingerprinted assets Name.<hash>.ext
    re.compile(r"index-[0-9a-f]{32}\.js"),            # served bundle
    re.compile(r"page@[0-9a-f]{32}"),                 # Playwright artifact names
    re.compile(r"\b[0-9a-f]{64}\b"),                  # full sha256
    re.compile(r"\b[0-9a-f]{8,16}\b"),                # source-sha / bundle-sha prefixes
]
```
Replace each match with a sentinel (`"\x00P%d\x00"`), run redaction, then restore. Verify after: bundle filename and at
least one asset fingerprint must appear unchanged in the published log.

## 3. Per-file redaction policy

Identifiers live in specific records only. Build logs carry asset hashes, not account ids — redacting them destroys the
build record for no privacy gain.

- id/slug/title redaction: capture logs, proxy/transport logs, harness run output, harness source.
- **path-only** redaction (home dir, workdir, export roots): build/export/npm logs, rig sources that carry no ids.
- Map ids to stable labels (`campaign-A … campaign-N`) plus a 12-hex `sha256` prefix, so a reader can still prove both
  takes used the *same* campaign without publishing it. Also redact campaign **titles** (`title <x>` → `<title-redacted>`).
  A 20-char mixed-case regex misses standalone 32-hex ids and slug ids (`spells-creation-10725`) — cover all three forms.
- Never publish: uid, tokens, service-account paths, emails. `uid_sha256_prefix` + `has_providers` + `disabled` is enough.

## 4. Identifiers burned into pixels and video

Captions injected into a take (`SIDE | baseline <sha> | candidate <sha> | campaign <id> | <utc>`) put the id inside both
the MP4 and every still. Text redaction cannot reach it.

1. Measure the caption band with PIL: scan rows from the top, mean brightness < ~60 = band; ink rows identify the line
   containing the id (typically line 2).
2. Re-encode a **derivative** with that line covered and redrawn:
   `-vf "drawbox=x=0:y=<Y>:w=iw:h=<H>:color=black@1:t=fill,drawtext=fontfile=<abs ttf>:textfile=<cap.txt>:x=7:y=<T>:fontsize=10:fontcolor=white"`
   Write line 2 as `campaign-A | <UTC timestamp>` — the timestamp is a recorded value, not a reconstruction.
3. Regenerate stills (`-ss 20 -frames:v 1`) and 1 Hz contact sheets (`fps=1,scale=120:-1,tile=8x8`) **from the
   derivative**, never from the original.
4. Verify two ways: `vision_analyze` reads the band back ("no 20-character id, timestamp intact"), and a pixel ink-run
   scan proves no leftover glyph fragments past the redrawn text (a too-narrow box leaves `:S`-shaped tails).
5. Label it: `derivative: re-encoded sanitized copy; caption line 2 redrawn; all other frames re-encoded from the same
   source video` — plus the original's sha256. A re-encode is not byte-identical and must not be described as the original.

## 5. Manifest and index that can actually verify

- `SHA256SUMS.txt` **must not list itself** — the line changes the file. Exclude it, use paths relative to the packet
  root, and publish the manifest's own sha256 in the delivery message (out-of-band).
- An `INDEX.json` that lives *inside* the packet and records the manifest hash is circular. Drop the manifest hash from
  the index entirely; record only counts and per-file original-vs-sanitized hashes.
- Stale numbers survive re-runs: an index written before the final manifest keeps the old `entries: N` and old hash.
  Regenerate the manifest **last**, then assert `wc -l SHA256SUMS.txt` equals the on-disk file count minus itself.
- Prove publication end-to-end, not just "uploaded": download the whole published prefix to a temp dir and run
  `shasum -a 256 -c SHA256SUMS.txt` there — expect `N OK`, 0 mismatches — plus `curl -o /dev/null -w '%{http_code}'`
  spot checks returning 200 with sha256 equal to local.

## 6. Derivation bugs: repair, don't re-run

A summary can be wrong while its source record is fine. Real case: `line.split()` on
`PROXY GET /api/settings -> 401 bytes=32` gives `['PROXY','GET','/api/settings','->','401','bytes=32']`; reading
`parts[3]` stored the literal arrow as `status` and `parts[4]` stored the HTTP code as `bytes`. Fixed indices are
`status=parts[4]`, `bytes=parts[5]`.

When repairing: request **counts usually stay identical** (only shifted fields were wrong) — say that explicitly so the
reviewer knows the ledger was not rebuilt. Cite `capture.py:<lines>` for the defect, the source log path, the source
log sha256, and the take's start line in the append-only capture log. Then state the corrected distribution per side.

Also expect side-to-side asymmetry to be real, not noise: one take can show `2× 401` while the other shows `0× 401`
(rate-limited `429`s answered before any auth challenge). Report it as observed rather than smoothing it into "401 in
both takes" — a reviewer will catch that sentence.

## 7. Records that never existed

Say it in the noun, not the passive voice:

- `/__whoami` body consumed in-process and never written → carry only the logged fields in `whoami-<side>.json` with
  `payload_was_persisted: false`.
- No SSE chunk records → "none exist beyond the single buffered request line; not reconstructed".
- Missing device admission receipts → cite the timestamps at which they stop.

Then substitute a **labelled fresh check** for the missing binding: recompute the bundle sha256 from the retained export
tree and mark it `fresh re-computation … not an original trace`. Never present a new observation as a recovered one.

## 8. Two harness traps that change what the evidence can claim

- **Buffered evidence proxy = no streaming proof.** A stdlib proxy that does `payload = resp.read()` then
  `send_header("Content-Length", …)` replays the SSE body as one response; the browser never receives partial chunks, so
  a `message-streaming-tail` sentinel can never render and `stream_detected: false` is a **rig** fact, not an app fact.
  State the consequence ("these takes prove pending→settle, not token-by-token streaming"). A streaming claim needs a
  chunk-preserving passthrough. Also verify the sentinel testid still exists in the app before blaming the selector.
- **Admin-minted custom token = injected token = supplementary.** `firebase_admin.auth.create_custom_token(uid)` →
  `signInWithCustomToken` → SDK persistence is *synthetic sign-in* under a repo rule that says "no auth bypass or
  injected tokens/state". What stays real: the backend tier, its enforcement (anon 401 → authed 200), the account, the
  renderer. What does not: the sign-in path. Say which, and that the primary visual lane is still open — do not let a
  successful capture imply acceptance.

## 9. Reply shape the reviewer expects

1. Headline verdict first, including any correction that changes their decision.
2. `item → fix` table mirroring their objections one-for-one.
3. Corrected artifact hashes, full length, per file.
4. Proof commands with observed output (verify count, leak-scan exit, HTTP codes, ffprobe).
5. "Still unproven (agreed, not contested)" — Cancel/Undo observed-but-never-clicked, continuous playback review,
   native-only geometry, streaming, genuine sign-in.
6. What was preserved privately, and where.
